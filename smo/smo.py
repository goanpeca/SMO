from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter, uniform_filter
from scipy.stats import rv_continuous, rv_histogram


def _rv(x: np.ndarray) -> rv_continuous:
    hist = np.histogram(x.flat, bins="auto")
    return rv_histogram(hist)


def _euclidean_norm(x: list[np.ndarray]) -> np.ndarray:
    if len(x) == 1:
        return np.abs(x[0])

    return np.sqrt(sum(xi ** 2 for xi in x))


def _filter(
    filter: callable, input: np.ndarray | np.ma.MaskedArray, **kwargs
) -> np.ma.MaskedArray:
    """Applies a scipy.ndimage filter respecting the mask.

    Parameters
    ----------
    filter : callable
        A scipy.ndimage filter, supporting `mode="constant"`.
    input : numpy.ndarray | numpy.ma.MaskedArray
        If it is not a MaskedArray, it is converted to a MaskedArray.

    Keyword arguments are passed to filter.

    Returns
    -------
    numpy.ma.MaskedArray
        The mask is shared with the input image.

    Notes
    -----
    Inspired on https://stackoverflow.com/a/36307291,
    which gives the same result as astropy.convolve.
    """
    if kwargs.get("output") is not None:
        raise ValueError("Argument output is not respected for MaskedArray.")

    # mask=None creates a np.zeros_like(input.data, bool) if no mask is provided.
    input = np.ma.MaskedArray(input, mask=None)

    out = filter(input.filled(0), **kwargs, mode="constant")
    norm = filter((~input.mask).astype(float), **kwargs, mode="constant")
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(input.mask, np.nan, out / norm)

    return np.ma.MaskedArray(out, input.mask)


def _normalized_gradient(input: np.ma.MaskedArray) -> list[np.ma.MaskedArray]:
    """Calculates the normalized gradient of a scalar field.

    Parameters
    ----------
    input : numpy.ma.MaskedArray
        Input field.

    Returns
    -------
    list of numpy.ma.MaskedArray
        The normalized gradient of the scalar field.
    """
    grad = np.gradient(input)

    if input.ndim == 1:
        return [np.sign(grad, out=grad)]

    norm = np.ma.MaskedArray(_euclidean_norm(grad), mask=input.mask)
    for x in grad:
        np.divide(x.data, norm.data, where=(norm > 0).filled(False), out=x.data)

    return [np.ma.MaskedArray(x.data, norm.mask) for x in grad]


def smo(
    input: np.ndarray | np.ma.MaskedArray, *, sigma: float, size: int
) -> np.ndarray | np.ma.MaskedArray:
    """Applies the Silver Mountain Operator (SMO) to a scalar field.

    Parameters
    ----------
    input : numpy.ndarray | numpy.ma.MaskedArray
        Input field.
    sigma : scalar or sequence of scalars
        Standard deviation for Gaussian kernel.
    size : int or sequence of int
        Averaging window size.

    Returns
    -------
    numpy.ndarray | numpy.ma.MaskedArray

    Notes
    -----
    Sigma and size are scale parameters,
    and should be less than the typical object size.
    """
    input = input.astype(float, copy=False)
    out = _filter(gaussian_filter, input, sigma=sigma)
    out = _normalized_gradient(out)
    out = [_filter(uniform_filter, x, size=size) for x in out]
    out = _euclidean_norm(out)

    if isinstance(input, np.ma.MaskedArray):
        return out
    else:
        return out.data


def smo_rv(
    shape: tuple[int, ...], *, sigma: float, size: int, random_state=None
) -> rv_continuous:
    """Generates a random variable of the SMO operator for a given sigma and size.

    Parameters
    ----------
    shape : tuple of ints
        Dimension of the random image to be generated.
    sigma : scalar or sequence of scalars
        Standard deviation for Gaussian kernel.
    size : int or sequence of int
        Averaging window size.
    random_state : numpy.random.Generator
        By default, numpy.random.default_rng(seed=42).

    Returns
    -------
    scipy.stats.rv_continuous.
    """
    if random_state is None:
        random_state = np.random.default_rng(seed=42)

    image = random_state.uniform(size=shape)
    smo_image = smo(image, sigma=sigma, size=size)
    return _rv(smo_image)
