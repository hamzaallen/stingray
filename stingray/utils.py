from __future__ import (absolute_import, unicode_literals, division,
                        print_function)
import sys
import collections

import warnings
import numpy as np
# If numba is installed, import jit. Otherwise, define an empty decorator with
# the same name.

try:
    from numba import jit
except:
    def jit(fun):
        return fun


class UnrecognizedMethod(Exception):
    pass


def simon(message, **kwargs):
    """The Statistical Interpretation MONitor.

    A warning system designed to always remind the user that Simon
    is watching him/her.

    Parameters
    ----------
    message : string
        The message that is thrown

    kwargs : dict
        The rest of the arguments that are passed to warnings.warn
    """
    
    warnings.warn("SIMON says: {0}".format(message), **kwargs)


def rebin_data(x, y, dx_new, method='sum'):

    """Rebin some data to an arbitrary new data resolution. Either sum
    the data points in the new bins or average them.

    Parameters
    ----------
    x: iterable
        The dependent variable with some resolution dx_old = x[1]-x[0]

    y: iterable
        The independent variable to be binned

    dx_new: float
        The new resolution of the dependent variable x

    method: {"sum" | "average" | "mean"}, optional, default "sum"
        The method to be used in binning. Either sum the samples y in
        each new bin of x, or take the arithmetic mean.


    Returns
    -------
    xbin: numpy.ndarray
        The midpoints of the new bins in x

    ybin: numpy.ndarray
        The binned quantity y
    """

    y = np.asarray(y)

    dx_old = x[1] - x[0]

    assert dx_new >= dx_old, "New frequency resolution must be larger than " \
                             "old frequency resolution."

    step_size = dx_new / dx_old

    output = []
    for i in np.arange(0, y.shape[0], step_size):
        total = 0

        int_i = int(i)
        prev_frac = int_i + 1 - i
        prev_bin = int_i
        total += prev_frac * y[prev_bin]

        if i + step_size < len(x):
            # Fractional part of next bin:
            next_frac = i + step_size - int(i + step_size)
            next_bin = int(i + step_size)
            total += next_frac * y[next_bin]

        total += sum(y[int(i+1):int(i+step_size)])
        output.append(total)

    output = np.asarray(output)

    if method in ['mean', 'avg', 'average', 'arithmetic mean']:
        ybin = output / np.float(step_size)

    elif method == "sum":
        ybin = output

    else:
        raise UnrecognizedMethod("Method for summing or averaging not recognized. "
                                 "Please enter either 'sum' or 'mean'.")

    tseg = x[-1] - x[0] + dx_old

    if (tseg / dx_new % 1) > 0:
        ybin = ybin[:-1]

    xbin = np.arange(ybin.shape[0]) * dx_new + x[0] - dx_old + dx_new

    return xbin, ybin, step_size


def assign_value_if_none(value, default):
    return default if value is None else value

def look_for_array_in_array(array1, array2):
    return next((i for i in array1 if i in array2), None)

def is_string(s):  # pragma : no cover
    """Portable function to answer this question."""
    
    PY2 = sys.version_info[0] == 2
    if PY2:
        return isinstance(s, basestring)  # NOQA
    else:
        return isinstance(s, str)  # NOQA


def is_iterable(stuff):
    """Test if stuff is an iterable."""
    
    return isinstance(stuff, collections.Iterable)

def order_list_of_arrays(data, order):
    if hasattr(data, 'items'):
        data = dict([(key, value[order])
                     for key, value in data.items()])
    elif is_iterable(data):
        data = [i[order] for i in data]
    else:
        data = None
    return data


def optimal_bin_time(fftlen, tbin):
    """Vary slightly the bin time to have a power of two number of bins.

    Given an FFT length and a proposed bin time, return a bin time
    slightly shorter than the original, that will produce a power-of-two number
    of FFT bins.
    """
    
    return fftlen / (2 ** np.ceil(np.log2(fftlen / tbin)))

def contiguous_regions(condition):
    """Find contiguous True regions of the boolean array "condition".

    Return a 2D array where the first column is the start index of the region
    and the second column is the end index.

    Parameters
    ----------
    condition : boolean array

    Returns
    -------
    idx : [[i0_0, i0_1], [i1_0, i1_1], ...]
        A list of integer couples, with the start and end of each True blocks
        in the original array

    Notes
    -----
    From : http://stackoverflow.com/questions/4494404/find-large-number-of-consecutive-values-
    fulfilling-condition-in-a-numpy-array
    """  

    # NOQA
    # Find the indicies of changes in "condition"
    diff = np.diff(condition)
    idx, = diff.nonzero()
    # We need to start things after the change in "condition". Therefore,
    # we'll shift the index by 1 to the right.
    idx += 1
    if condition[0]:
        # If the start of condition is True prepend a 0
        idx = np.r_[0, idx]
    if condition[-1]:
        # If the end of condition is True, append the length of the array
        idx = np.r_[idx, condition.size]
    # Reshape the result into two columns
    idx.shape = (-1, 2)
    return idx


def time_intervals_from_gtis(gtis, chunk_length):
    """Returns equal time intervals compatible with GTIs.

    Used to start each FFT/PDS/cospectrum from the start of a GTI,
    and stop before the next gap in data (end of GTI).

    Parameters
    ----------
    gtis : [[gti0_0, gti0_1], [gti1_0, gti1_1], ...]
    chunk_length : float
        Length of the chunks

    Returns
    -------
    spectrum_start_times : array-like
        List of starting times to use in the spectral calculations.

    spectrum_stop_times : array-like
        List of end times to use in the spectral calculations.

    """
    spectrum_start_times = np.array([], dtype=np.longdouble)
    for g in gtis:
        if g[1] - g[0] < chunk_length:
            continue

        newtimes = np.arange(g[0], g[1] - chunk_length,
                             np.longdouble(chunk_length),
                             dtype=np.longdouble)
        spectrum_start_times = \
            np.append(spectrum_start_times,
                      newtimes)

    assert len(spectrum_start_times) > 0, \
        ("No GTIs are equal to or longer than chunk_length.")
    return spectrum_start_times, spectrum_start_times + chunk_length


def bin_intervals_from_gtis(gtis, chunk_length, time):
    """Similar to intervals_from_gtis, but given an input time array.

    Used to start each FFT/PDS/cospectrum from the start of a GTI,
    and stop before the next gap in data (end of GTI).
    In this case, it is necessary to specify the time array containing the
    times of the light curve bins.
    Returns start and stop bins of the intervals to use for the PDS

    Parameters
    ----------
    gtis : [[gti0_0, gti0_1], [gti1_0, gti1_1], ...]
    chunk_length : float
        Length of the chunks
    time : array-like
        Times of light curve bins

    Returns
    -------
    spectrum_start_bins : array-like
        List of starting bins in the original time array to use in spectral
        calculations.

    spectrum_stop_bins : array-like
        List of end bins to use in the spectral calculations.
    """
    bintime = time[1] - time[0]
    nbin = np.long(chunk_length / bintime)

    spectrum_start_bins = np.array([], dtype=np.long)
    for g in gtis:
        if g[1] - g[0] < chunk_length:
            continue
        good = (time - bintime / 2 > g[0])&(time + bintime / 2 < g[1])
        t_good = time[good]
        if len(t_good) == 0:
            continue
        startbin = np.argmin(np.abs(time - bintime / 2 - g[0]))
        stopbin = np.argmin(np.abs(time + bintime / 2 - g[1]))

        if time[startbin] < g[0]: startbin += 1
        if time[stopbin] < g[1] + bintime/2: stopbin += 1

        newbins = np.arange(startbin, stopbin - nbin + 1, nbin,
                            dtype=np.long)
        spectrum_start_bins = \
            np.append(spectrum_start_bins,
                      newbins)
    assert len(spectrum_start_bins) > 0, \
        ("No GTIs are equal to or longer than chunk_length.")
    return spectrum_start_bins, spectrum_start_bins + nbin
