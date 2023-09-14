"""Base classes"""
from __future__ import annotations

from collections.abc import Iterable
import pickle
import warnings
import copy

import numpy as np
from astropy.table import Table
from astropy.time import Time, TimeDelta
from astropy.units import Quantity

from typing import TYPE_CHECKING, Type, TypeVar, Union

if TYPE_CHECKING:
    from xarray import Dataset
    from pandas import DataFrame
    from astropy.timeseries import TimeSeries
    from astropy.time import TimeDelta
    import numpy.typing as npt

    TTime = Union[Time, TimeDelta, Quantity, npt.ArrayLike]
    Tso = TypeVar("Tso", bound="StingrayObject")


class StingrayObject(object):
    """This base class defines some general-purpose utilities.

    The main purpose is to have a consistent mechanism for:

    + round-tripping to and from Astropy Tables and other dataframes

    + round-tripping to files in different formats

    The idea is that any object inheriting :class:`StingrayObject` should,
    just by defining an attribute called ``main_array_attr``, be able to perform
    the operations above, with no additional effort.

    ``main_array_attr`` is, e.g. ``time`` for :class:`EventList` and
    :class:`Lightcurve`, ``freq`` for :class:`Crossspectrum`, ``energy`` for
    :class:`VarEnergySpectrum`, and so on. It is the array with wich all other
    attributes are compared: if they are of the same shape, they get saved as
    columns of the table/dataframe, otherwise as metadata.
    """

    def __init__(cls, *args, **kwargs) -> None:
        if not hasattr(cls, "main_array_attr"):
            raise RuntimeError(
                "A StingrayObject needs to have the main_array_attr attribute specified"
            )

    def array_attrs(self) -> list[str]:
        """List the names of the array attributes of the Stingray Object.

        By array attributes, we mean the ones with the same size and shape as
        ``main_array_attr`` (e.g. ``time`` in ``EventList``)
        """

        main_attr = getattr(self, getattr(self, "main_array_attr"))
        if main_attr is None:
            return []

        return [
            attr
            for attr in dir(self)
            if (
                isinstance(getattr(self, attr), Iterable)
                and np.shape(getattr(self, attr)) == np.shape(main_attr)
            )
        ]

    def meta_attrs(self) -> list[str]:
        """List the names of the meta attributes of the Stingray Object.

        By array attributes, we mean the ones with a different size and shape
        than ``main_array_attr`` (e.g. ``time`` in ``EventList``)
        """
        array_attrs = self.array_attrs()
        return [
            attr
            for attr in dir(self)
            if (
                attr not in array_attrs
                and not attr.startswith("_")
                # Use new assignment expression (PEP 572). I'm testing that
                # self.attribute is not callable, and assigning its value to
                # the variable attr_value for further checks
                and not callable(attr_value := getattr(self, attr))
                # a way to avoid EventLists, Lightcurves, etc.
                and not hasattr(attr_value, "meta_attrs")
            )
        ]

    def get_meta_dict(self) -> dict:
        """Give a dictionary with all non-None meta attrs of the object."""
        meta_attrs = self.meta_attrs()
        meta_dict = {}
        for key in meta_attrs:
            val = getattr(self, key)
            if val is not None:
                meta_dict[key] = val
        return meta_dict

    def to_astropy_table(self) -> Table:
        """Create an Astropy Table from a ``StingrayObject``

        Array attributes (e.g. ``time``, ``pi``, ``energy``, etc. for
        ``EventList``) are converted into columns, while meta attributes
        (``mjdref``, ``gti``, etc.) are saved into the ``meta`` dictionary.
        """
        data = {}
        array_attrs = self.array_attrs()

        for attr in array_attrs:
            data[attr] = np.asarray(getattr(self, attr))

        ts = Table(data)

        ts.meta.update(self.get_meta_dict())

        return ts

    @classmethod
    def from_astropy_table(cls: Type[Tso], ts: Table) -> Tso:
        """Create a Stingray Object object from data in an Astropy Table.

        The table MUST contain at least a column named like the
        ``main_array_attr``.
        The rest of columns will form the array attributes of the
        new object, while the attributes in ds.attrs will
        form the new meta attributes of the object.

        It is strongly advisable to define such attributes and columns
        using the standard attributes of the wanted StingrayObject (e.g.
        ``time``, ``pi``, etc. for ``EventList``)
        """
        cls = cls()

        if len(ts) == 0:
            # return an empty object
            return cls

        array_attrs = ts.colnames

        # Set the main attribute first
        mainarray = np.array(ts[cls.main_array_attr])  # type: ignore
        setattr(cls, cls.main_array_attr, mainarray)  # type: ignore

        for attr in array_attrs:
            if attr == cls.main_array_attr:  # type: ignore
                continue
            setattr(cls, attr.lower(), np.array(ts[attr]))

        for key, val in ts.meta.items():
            setattr(cls, key.lower(), val)

        return cls

    def to_xarray(self) -> Dataset:
        """Create an ``xarray`` Dataset from a `StingrayObject`.

        Array attributes (e.g. ``time``, ``pi``, ``energy``, etc. for
        ``EventList``) are converted into columns, while meta attributes
        (``mjdref``, ``gti``, etc.) are saved into the ``ds.attrs`` dictionary.
        """
        from xarray import Dataset

        data = {}
        array_attrs = self.array_attrs()

        for attr in array_attrs:
            data[attr] = np.asarray(getattr(self, attr))

        ts = Dataset(data)

        ts.attrs.update(self.get_meta_dict())

        return ts

    @classmethod
    def from_xarray(cls: Type[Tso], ts: Dataset) -> Tso:
        """Create a `StingrayObject` from data in an xarray Dataset.

        The dataset MUST contain at least a column named like the
        ``main_array_attr``.
        The rest of columns will form the array attributes of the
        new object, while the attributes in ds.attrs will
        form the new meta attributes of the object.

        It is strongly advisable to define such attributes and columns
        using the standard attributes of the wanted StingrayObject (e.g.
        ``time``, ``pi``, etc. for ``EventList``)
        """
        cls = cls()

        if len(ts[cls.main_array_attr]) == 0:  # type: ignore
            # return an empty object
            return cls

        array_attrs = ts.coords

        # Set the main attribute first
        mainarray = np.array(ts[cls.main_array_attr])  # type: ignore
        setattr(cls, cls.main_array_attr, mainarray)  # type: ignore

        for attr in array_attrs:
            if attr == cls.main_array_attr:  # type: ignore
                continue
            setattr(cls, attr, np.array(ts[attr]))

        for key, val in ts.attrs.items():
            if key not in array_attrs:
                setattr(cls, key, val)

        return cls

    def to_pandas(self) -> DataFrame:
        """Create a pandas ``DataFrame`` from a :class:`StingrayObject`.

        Array attributes (e.g. ``time``, ``pi``, ``energy``, etc. for
        ``EventList``) are converted into columns, while meta attributes
        (``mjdref``, ``gti``, etc.) are saved into the ``ds.attrs`` dictionary.
        """
        from pandas import DataFrame

        data = {}
        array_attrs = self.array_attrs()

        for attr in array_attrs:
            data[attr] = np.asarray(getattr(self, attr))

        ts = DataFrame(data)

        ts.attrs.update(self.get_meta_dict())

        return ts

    @classmethod
    def from_pandas(cls: Type[Tso], ts: DataFrame) -> Tso:
        """Create an `StingrayObject` object from data in a pandas DataFrame.

        The dataframe MUST contain at least a column named like the
        ``main_array_attr``.
        The rest of columns will form the array attributes of the
        new object, while the attributes in ds.attrs will
        form the new meta attributes of the object.

        It is strongly advisable to define such attributes and columns
        using the standard attributes of the wanted StingrayObject (e.g.
        ``time``, ``pi``, etc. for ``EventList``)

        """
        cls = cls()

        if len(ts) == 0:
            # return an empty object
            return cls

        array_attrs = ts.columns

        # Set the main attribute first
        mainarray = np.array(ts[cls.main_array_attr])  # type: ignore
        setattr(cls, cls.main_array_attr, mainarray)  # type: ignore

        for attr in array_attrs:
            if attr == cls.main_array_attr:  # type: ignore
                continue
            setattr(cls, attr, np.array(ts[attr]))

        for key, val in ts.attrs.items():
            if key not in array_attrs:
                setattr(cls, key, val)

        return cls

    @classmethod
    def read(cls: Type[Tso], filename: str, fmt: str = None) -> Tso:
        r"""Generic reader for :class`StingrayObject`

        Currently supported formats are

        * pickle (not recommended for long-term storage)
        * any other formats compatible with the writers in
          :class:`astropy.table.Table` (ascii.ecsv, hdf5, etc.)

        Files that need the :class:`astropy.table.Table` interface MUST contain
        at least a column named like the ``main_array_attr``.
        The default ascii format is enhanced CSV (ECSV). Data formats
        supporting the serialization of metadata (such as ECSV and HDF5) can
        contain all attributes such as ``mission``, ``gti``, etc with
        no significant loss of information. Other file formats might lose part
        of the metadata, so must be used with care.

        ..note::

            Complex values can be dealt with out-of-the-box in some formats
            like HDF5 or FITS, not in others (e.g. all ASCII formats).
            With these formats, and in any case when fmt is ``None``, complex
            values should be stored as two columns of real numbers, whose names
            are of the format <variablename>.real and <variablename>.imag

        Parameters
        ----------
        filename: str
            Path and file name for the file to be read.

        fmt: str
            Available options are 'pickle', 'hea', and any `Table`-supported
            format such as 'hdf5', 'ascii.ecsv', etc.

        Returns
        -------
        obj: :class:`StingrayObject` object
            The object reconstructed from file
        """

        if fmt is None:
            pass
        elif fmt.lower() == "pickle":
            with open(filename, "rb") as fobj:
                return pickle.load(fobj)
        elif fmt.lower() == "ascii":
            fmt = "ascii.ecsv"

        ts = Table.read(filename, format=fmt)

        # For specific formats, and in any case when the format is not
        # specified, make sure that complex values are treated correctly.
        if fmt is None or "ascii" in fmt:
            for col in ts.colnames:
                if not ((is_real := col.endswith(".real")) or (is_imag := col.endswith(".imag"))):
                    continue

                new_value = ts[col]

                if is_imag:
                    new_value = new_value * 1j

                # Make sure it's complex, even if we find the real part first
                new_value = new_value + 0.0j

                col_strip = col.replace(".real", "").replace(".imag", "")

                if col_strip not in ts.colnames:
                    # If the column without ".real" or ".imag" doesn't exist,
                    # define it, and make sure it's complex-valued
                    ts[col_strip] = new_value
                else:
                    # If it does exist, sum the new value to it.
                    ts[col_strip] += new_value

                ts.remove_column(col)

        return cls.from_astropy_table(ts)

    def write(self, filename: str, fmt: str = None) -> None:
        """Generic writer for :class`StingrayObject`

        Currently supported formats are

        * pickle (not recommended for long-term storage)
        * any other formats compatible with the writers in
          :class:`astropy.table.Table` (ascii.ecsv, hdf5, etc.)

        ..note::

            Complex values can be dealt with out-of-the-box in some formats
            like HDF5 or FITS, not in others (e.g. all ASCII formats).
            With these formats, and in any case when fmt is ``None``, complex
            values will be stored as two columns of real numbers, whose names
            are of the format <variablename>.real and <variablename>.imag

        Parameters
        ----------
        filename: str
            Name and path of the file to save the object list to.

        fmt: str
            The file format to store the data in.
            Available options are ``pickle``, ``hdf5``, ``ascii``, ``fits``
        """

        if fmt is None:
            pass
        elif fmt.lower() == "pickle":
            with open(filename, "wb") as fobj:
                pickle.dump(self, fobj)
            return
        elif fmt.lower() == "ascii":
            fmt = "ascii.ecsv"

        ts = self.to_astropy_table()
        if fmt is None or "ascii" in fmt:
            for col in ts.colnames:
                if np.iscomplex(ts[col][0]):
                    ts[f"{col}.real"] = ts[col].real
                    ts[f"{col}.imag"] = ts[col].imag
                    ts.remove_column(col)

        try:
            ts.write(filename, format=fmt, overwrite=True, serialize_meta=True)
        except TypeError:
            ts.write(filename, format=fmt, overwrite=True)


class StingrayTimeseries(StingrayObject):
    main_array_attr = "time"

    def __init__(
        self,
        time: TTime = None,
        array_attrs: dict = {},
        mjdref: TTime = 0,
        notes: str = "",
        gti: npt.ArrayLike = None,
        high_precision: bool = False,
        ephem: str = None,
        timeref: str = None,
        timesys: str = None,
        **other_kw,
    ):
        StingrayObject.__init__(self)

        self.notes = notes
        self.mjdref = mjdref
        self.gti = np.asarray(gti) if gti is not None else None
        self.ephem = ephem
        self.timeref = timeref
        self.timesys = timesys
        self._mask = None
        self.dt = other_kw.pop("dt", 0)

        if time is not None:
            time, mjdref = interpret_times(time, mjdref)
            if not high_precision:
                self.time = np.asarray(time)
            else:
                self.time = np.asarray(time, dtype=np.longdouble)
            self.ncounts = self.time.size
        else:
            self.time = None

        for kw in other_kw:
            setattr(self, kw, other_kw[kw])
        for kw in array_attrs:
            new_arr = np.asarray(array_attrs[kw])
            if self.time.size != new_arr.size:
                raise ValueError(f"Lengths of time and {kw} must be equal.")
            setattr(self, kw, new_arr)

    def apply_mask(self, mask: npt.ArrayLike, inplace: bool = False, filtered_attrs: list = None):
        """Apply a mask to all array attributes of the time series

        Parameters
        ----------
        mask : array of ``bool``
            The mask. Has to be of the same length as ``self.time``

        Other parameters
        ----------------
        inplace : bool
            If True, overwrite the current light curve. Otherwise, return a new one.
        filtered_attrs : list of str or None
            Array attributes to be filtered. Defaults to all array attributes if ``None``.
            The other array attributes will be discarded from the time series to avoid
            inconsistencies. Time is always included.

        Examples
        --------
        >>> ts = StingrayTimeseries(time=[0, 1, 2], array_attrs={"counts": [2, 3, 4]}, mission="nustar")
        >>> ts.bubuattr = [222, 111, 333]  # Add another array attr
        >>> newts0 = ts.apply_mask([True, True, False], inplace=False);
        >>> newts1 = ts.apply_mask([True, True, False], inplace=True);
        >>> newts0.mission == "nustar"
        True
        >>> np.altslose(newts0.time, [0, 1])
        True
        >>> np.altslose(newts0.bubuattr, [222, 111])
        True
        >>> np.altslose(newts1.time, [0, 1])
        True
        >>> ts is newts1
        True
        """
        all_attrs = self.array_attrs()
        if filtered_attrs is None:
            filtered_attrs = all_attrs
        if "time" not in filtered_attrs:
            filtered_attrs.append("time")

        if inplace:
            new_ts = self
            # Eliminate all unfiltered attributes
            for attr in all_attrs:
                if attr not in filtered_attrs:
                    setattr(new_ts, attr, None)
        else:
            new_ts = type(self)()
            for attr in self.meta_attrs():
                try:
                    setattr(new_ts, attr, copy.deepcopy(getattr(self, attr)))
                except AttributeError:
                    continue

        for attr in filtered_attrs:
            setattr(new_ts, attr, copy.deepcopy(np.asarray(getattr(self, attr)[mask])))
        return new_ts

    def apply_gtis(self, inplace: bool = True):
        """
        Apply GTIs to a light curve. Filters the ``time``, ``counts``,
        ``countrate``, ``counts_err`` and ``countrate_err`` arrays for all bins
        that fall into Good Time Intervals and recalculates mean countrate
        and the number of bins.

        If the data already have

        Parameters
        ----------
        inplace : bool
            If True, overwrite the current light curve. Otherwise, return a new one.

        """
        # I import here to avoid the risk of circular imports
        from .gti import check_gtis, create_gti_mask

        check_gtis(self.gti)

        # This will automatically be recreated from GTIs once I set it to None
        good = create_gti_mask(self.time, self.gti, dt=self.dt)
        newts = self.apply_mask(good, inplace=inplace)
        return newts

    def split_by_gti(self, gti=None, min_points=2):
        """
        Split the current :class:`StingrayTimeseries` object into a list of
        :class:`StingrayTimeseries` objects, one for each continuous GTI segment
        as defined in the ``gti`` attribute.

        Parameters
        ----------
        min_points : int, default 1
            The minimum number of data points in each light curve. Light
            curves with fewer data points will be ignored.

        Returns
        -------
        list_of_tss : list
            A list of :class:`Lightcurve` objects, one for each GTI segment
        """
        from .gti import gti_border_bins, create_gti_mask

        if gti is None:
            gti = self.gti

        list_of_tss = []

        start_bins, stop_bins = gti_border_bins(gti, self.time, self.dt)
        for i in range(len(start_bins)):
            start = start_bins[i]
            stop = stop_bins[i]

            if (stop - start) < min_points:
                continue

            new_gti = np.array([gti[i]])
            mask = create_gti_mask(self.time, new_gti)

            # Note: GTIs are consistent with default in this case!
            new_ts = self.apply_mask(mask)
            new_ts.gti = new_gti

            list_of_tss.append(new_ts)

        return list_of_tss

    def to_astropy_timeseries(self) -> TimeSeries:
        """Save the ``StingrayTimeseries`` to an ``Astropy`` timeseries.

        Array attributes (time, pi, energy, etc.) are converted
        into columns, while meta attributes (mjdref, gti, etc.)
        are saved into the ``meta`` dictionary.

        Returns
        -------
        ts : `astropy.timeseries.TimeSeries`
            A ``TimeSeries`` object with the array attributes as columns,
            and the meta attributes in the `meta` dictionary
        """
        from astropy.timeseries import TimeSeries
        from astropy.time import TimeDelta
        from astropy import units as u

        data = {}
        array_attrs = self.array_attrs()

        for attr in array_attrs:
            if attr == "time":
                continue
            data[attr] = np.asarray(getattr(self, attr))

        if data == {}:
            data = None

        if self.time is not None and np.size(self.time) > 0:  # type: ignore
            times = TimeDelta(self.time * u.s)  # type: ignore
            ts = TimeSeries(data=data, time=times)
        else:
            ts = TimeSeries()

        ts.meta.update(self.get_meta_dict())

        return ts

    @classmethod
    def from_astropy_timeseries(cls, ts: TimeSeries) -> StingrayTimeseries:
        """Create a `StingrayTimeseries` from data in an Astropy TimeSeries

        The timeseries has to define at least a column called time,
        the rest of columns will form the array attributes of the
        new event list, while the attributes in table.meta will
        form the new meta attributes of the event list.

        It is strongly advisable to define such attributes and columns
        using the standard attributes of EventList: time, pi, energy, gti etc.

        Parameters
        ----------
        ts : `astropy.timeseries.TimeSeries`
            A ``TimeSeries`` object with the array attributes as columns,
            and the meta attributes in the `meta` dictionary

        Returns
        -------
        ts : `StingrayTimeseries`
            Timeseries object
        """

        time = ts["time"]
        mjdref = None
        if "mjdref" in ts.meta:
            mjdref = ts.meta["mjdref"]

        new_cls = cls()
        time, mjdref = interpret_times(time, mjdref)
        new_cls.time = np.asarray(time)  # type: ignore

        array_attrs = ts.colnames
        for key, val in ts.meta.items():
            setattr(new_cls, key, val)

        for attr in array_attrs:
            if attr == "time":
                continue
            setattr(new_cls, attr, np.asarray(ts[attr]))

        return new_cls

    def change_mjdref(self, new_mjdref: float) -> StingrayTimeseries:
        """Change the MJD reference time (MJDREF) of the time series

        The times of the time series will be shifted in order to be referred to
        this new MJDREF

        Parameters
        ----------
        new_mjdref : float
            New MJDREF

        Returns
        -------
        new_ts : :class:`StingrayTimeseries` object
            The new time series, shifted by MJDREF
        """
        time_shift = (self.mjdref - new_mjdref) * 86400  # type: ignore

        ts = self.shift(time_shift)
        ts.mjdref = new_mjdref  # type: ignore
        return ts

    def shift(self, time_shift: float) -> StingrayTimeseries:
        """Shift the time and the GTIs by the same amount

        Parameters
        ----------
        time_shift: float
            The time interval by which the light curve will be shifted (in
            the same units as the time array in :class:`Lightcurve`

        Returns
        -------
        ts : ``StingrayTimeseries`` object
            The new time series shifted by ``time_shift``

        """
        ts = copy.deepcopy(self)
        ts.time = np.asarray(ts.time) + time_shift  # type: ignore
        if hasattr(ts, "gti"):
            ts.gti = np.asarray(ts.gti) + time_shift  # type: ignore

        return ts


def interpret_times(time: TTime, mjdref: float = 0) -> tuple[npt.ArrayLike, float]:
    """Understand the format of input times, and return seconds from MJDREF

    Parameters
    ----------
    time : class:`astropy.Time`, class:`time.Time`, class:`astropy.TimeDelta`, class:`astropy.Quantity`, class:`np.array`
        Input times.

    Other Parameters
    ----------------
    mjdref : float
        Input MJD reference of the times. Optional.

    Returns
    -------
    time_s : class:`np.array`
        Times, in seconds from MJDREF
    mjdref : float
        MJDREF. If the input time is a `time.Time` object and the input mjdref
        is 0, it will be defined as the MJD of the input time.

    Examples
    --------
    >>> import astropy.units as u
    >>> time = Time(57483, format='mjd')
    >>> newt, mjdref = interpret_times(time)
    >>> newt == 0
    True
    >>> mjdref == 57483
    True
    >>> time = Time([57483], format='mjd')
    >>> newt, mjdref = interpret_times(time)
    >>> np.allclose(newt, 0)
    True
    >>> mjdref == 57483
    True
    >>> time = TimeDelta([3, 4, 5] * u.s)
    >>> newt, mjdref = interpret_times(time)
    >>> np.allclose(newt, [3, 4, 5])
    True
    >>> time = np.array([3, 4, 5])
    >>> newt, mjdref = interpret_times(time, mjdref=45000)
    >>> np.allclose(newt, [3, 4, 5])
    True
    >>> mjdref == 45000
    True
    >>> time = np.array([3, 4, 5] * u.s)
    >>> newt, mjdref = interpret_times(time, mjdref=45000)
    >>> np.allclose(newt, [3, 4, 5])
    True
    >>> mjdref == 45000
    True
    >>> newt, mjdref = interpret_times(1, mjdref=45000)
    >>> newt == 1
    True
    >>> newt, mjdref = interpret_times(list, mjdref=45000)
    Traceback (most recent call last):
    ...
    ValueError: Unknown time format: ...
    >>> newt, mjdref = interpret_times("guadfkljfd", mjdref=45000)
    Traceback (most recent call last):
    ...
    ValueError: Unknown time format: ...
    """
    if isinstance(time, TimeDelta):
        out_times = time.to("s").value
        return out_times, mjdref

    if isinstance(time, Time):
        mjds = time.mjd
        if mjdref == 0:
            if np.all(mjds > 10000):
                if isinstance(mjds, Iterable):
                    mjdref = mjds[0]
                else:
                    mjdref = mjds

        out_times = (mjds - mjdref) * 86400
        return out_times, mjdref

    if isinstance(time, Quantity):
        out_times = time.to("s").value
        return out_times, mjdref

    if isinstance(time, (tuple, list, np.ndarray)):
        return time, mjdref

    if not isinstance(time, Iterable):
        try:
            float(time)
            return time, mjdref
        except (ValueError, TypeError):
            pass

    raise ValueError(f"Unknown time format: {type(time)}")
