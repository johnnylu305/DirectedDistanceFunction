"""
SH from se3-transformer which is faster than scipy version
https://github.com/lucidrains/se3-transformer-pytorch/blob/main/se3_transformer_pytorch/spherical_harmonics.py
"""
from math import pi, sqrt
from functools import reduce
from operator import mul
import torch
from functools import wraps, lru_cache


# caching functions

def cache(cache, key_fn):
    def cache_inner(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            key_name = key_fn(*args, **kwargs)
            if key_name in cache:
                return cache[key_name]
            res = fn(*args, **kwargs)
            cache[key_name] = res
            return res

        return inner
    return cache_inner

# constants

CACHE = {}

def clear_spherical_harmonics_cache():
    CACHE.clear()

def lpmv_cache_key_fn(l, m, x):
    return (l, m)

# spherical harmonics

@lru_cache(maxsize = 1000)
def semifactorial(x):
    return reduce(mul, range(x, 1, -2), 1.)

@lru_cache(maxsize = 1000)
def pochhammer(x, k):
    return reduce(mul, range(x + 1, x + k), float(x))

def negative_lpmv(l, m, y):
    if m < 0:
        y *= ((-1) ** m / pochhammer(l + m + 1, -2 * m))
    return y

@cache(cache = CACHE, key_fn = lpmv_cache_key_fn)
def lpmv(l, m, x):
    """Associated Legendre function including Condon-Shortley phase.
    Args:
        m: int order 
        l: int degree
        x: float argument tensor
    Returns:
        tensor of x-shape
    """
    # Check memoized versions
    m_abs = abs(m)

    if m_abs > l:
        return None

    if l == 0:
        return torch.ones_like(x)
    
    # Check if on boundary else recurse solution down to boundary
    if m_abs == l:
        # Compute P_m^m
        y = (-1)**m_abs * semifactorial(2*m_abs-1)
        y *= torch.pow(1-x*x, m_abs/2)
        return negative_lpmv(l, m, y)

    # Recursively precompute lower degree harmonics
    lpmv(l-1, m, x)

    # Compute P_{l}^m from recursion in P_{l-1}^m and P_{l-2}^m
    # Inplace speedup
    y = ((2*l-1) / (l-m_abs)) * x * lpmv(l-1, m_abs, x)

    if l - m_abs > 1:
        y -= ((l+m_abs-1)/(l-m_abs)) * CACHE[(l-2, m_abs)]
    
    if m < 0:
        y = self.negative_lpmv(l, m, y)
    return y

def get_spherical_harmonics_element(l, m, theta, phi):
    """Tesseral spherical harmonic with Condon-Shortley phase.
    The Tesseral spherical harmonics are also known as the real spherical
    harmonics.
    Args:
        l: int for degree
        m: int for order, where -l <= m < l
        theta: collatitude or polar angle
        phi: longitude or azimuth
    Returns:
        tensor of shape theta
    """
    m_abs = abs(m)
    assert m_abs <= l, "absolute value of order m must be <= degree l"

    N = sqrt((2*l + 1) / (4 * pi))
    leg = lpmv(l, m_abs, torch.cos(theta))

    if m == 0:
        return N * leg

    if m > 0:
        Y = torch.cos(m * phi)
    else:
        Y = torch.sin(m_abs * phi)

    Y *= leg
    N *= sqrt(2. / pochhammer(l - m_abs + 1, 2 * m_abs))
    Y *= N
    return Y

def get_spherical_harmonics(l, theta, phi):
    """ Tesseral harmonic with Condon-Shortley phase.
    The Tesseral spherical harmonics are also known as the real spherical
    harmonics.
    Args:
        l: int for degree
        theta: collatitude or polar angle
        phi: longitude or azimuth
    Returns:
        tensor of shape [*theta.shape, 2*l+1]
    """
    return torch.stack([ get_spherical_harmonics_element(l, m, theta, phi) \
                         for m in range(-l, l+1) ],
                        dim = -1)

def cart_to_sphere(cart):
    """
    Map cartesian to sphere coordinate
    The arbitrary cases will be defined by atan2
        ex: (0, 0, 0) to (r, 0.7854, 0.9553)
    """
    # -pi~pi
    phi = torch.atan2(cart[:,1], cart[:,0])
    # 0~2pi
    phi = (phi+torch.tensor(2*pi))%torch.tensor(2*pi)
    # 0~pi
    theta = torch.arccos(cart[:,2]/torch.sqrt(torch.sum(torch.square(cart+1e-10), dim=1)))
    return theta, phi

def sh_linear_combination(degree, cart, coefficients):
    """
    Linear combination of SH
    """
    clear_spherical_harmonics_cache()
    b = cart.size()[0]
    num_basis = (2*degree+2)*(degree+1)//2
    theta, phi = cart_to_sphere(cart)   

    sh = get_spherical_harmonics(0, theta, phi)
    for i in range(1, degree+1):
        sh = torch.hstack([sh, get_spherical_harmonics(i, theta, phi)])
    
    linear_comb = torch.bmm(coefficients.view(b, 1, num_basis), sh.view(b, num_basis, 1).detach()).view(b)
    return linear_comb

if __name__=="__main__":
    degree = 3
    num_basis = (2*degree+2)*(degree+1)//2
    print("[ INFO ]: {} basis".format(num_basis))

    coords = torch.tensor([[0.0, 0.0, 0.0], 
                           [1.0, 1.0, 1.0], 
                           [2.0, 2.0, 2.0],
                           [2.5, 1.3, 2.1]])
    b = coords.size()[0]
    coefficients = torch.rand((b, num_basis))
    depths = sh_linear_combination(degree, coords, coefficients)
    print(depths)

    coords = torch.tensor([[1.0, 0.0, 0.0], 
                           [1.0, 2.0, -1.0], 
                           [3.0, 2.0, -2.0]])
    b = coords.size()[0]
    coefficients = torch.rand((b, num_basis))
    depths = sh_linear_combination(degree, coords, coefficients)
    print(depths)
