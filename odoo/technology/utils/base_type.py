from collections.abc import Collection
from collections.abc import Iterable, Iterator, Mapping, MutableMapping, MutableSet, Reversible
import typing
from functools import reduce, wraps
import itertools

#########################################################################
#                       basic algorithm
#########################################################################
def freehash(arg: typing.Any) -> int:
    try:
        return hash(arg)
    except Exception:
        if isinstance(arg, Mapping):
            return hash(frozendict(arg))
        elif isinstance(arg, Iterable):
            return hash(frozenset(freehash(item) for item in arg))
        else:
            return id(arg)

#########################################################################
#                       basic types
#########################################################################

K = typing.TypeVar('K')
T = typing.TypeVar('T')

class Collector(dict[K, tuple[T, ...]], typing.Generic[K, T]):
    """ A mapping from keys to tuples.  This implements a relation, and can be
        seen as a space optimization for ``defaultdict(tuple)``.
    """
    __slots__ = ()

    def __getitem__(self, key: K) -> tuple[T, ...]:
        return self.get(key, ())

    def __setitem__(self, key: K, val: Iterable[T]):
        val = tuple(val)
        if val:
            super().__setitem__(key, val)
        else:
            super().pop(key, None)

    def add(self, key: K, val: T):
        vals = self[key]
        if val not in vals:
            self[key] = vals + (val,)

    def discard_keys_and_values(self, excludes: Collection[K | T]) -> None:
        for key in excludes:
            self.pop(key, None)  # type: ignore
        for key, vals in list(self.items()):
            self[key] = tuple(val for val in vals if val not in excludes)  # type: ignore

class frozendict(dict[K, T], typing.Generic[K, T]):
    """ An implementation of an immutable dictionary. """
    __slots__ = ()

    def __delitem__(self, key):
        raise NotImplementedError("'__delitem__' not supported on frozendict")

    def __setitem__(self, key, val):
        raise NotImplementedError("'__setitem__' not supported on frozendict")

    def clear(self):
        raise NotImplementedError("'clear' not supported on frozendict")

    def pop(self, key, default=None):
        raise NotImplementedError("'pop' not supported on frozendict")

    def popitem(self):
        raise NotImplementedError("'popitem' not supported on frozendict")

    def setdefault(self, key, default=None):
        raise NotImplementedError("'setdefault' not supported on frozendict")

    def update(self, *args, **kwargs):
        raise NotImplementedError("'update' not supported on frozendict")

    def __hash__(self) -> int:  # type: ignore
        return hash(frozenset((key, freehash(val)) for key, val in self.items()))


class DotDict(dict):
    """Helper for dot.notation access to dictionary attributes

        E.g.
          foo = DotDict({'bar': False})
          return foo.bar
    """
    def __getattr__(self, attrib):
        val = self.get(attrib)
        return DotDict(val) if isinstance(val, dict) else val


class ReadonlyDict(Mapping[K, T], typing.Generic[K, T]):
    """Helper for an unmodifiable dictionary, not even updatable using `dict.update`.

    This is similar to a `frozendict`, with one drawback and one advantage:

    - `dict.update` works for a `frozendict` but not for a `ReadonlyDict`.
    - `json.dumps` works for a `frozendict` by default but not for a `ReadonlyDict`.

    This comes from the fact `frozendict` inherits from `dict`
    while `ReadonlyDict` inherits from `collections.abc.Mapping`.

    So, depending on your needs,
    whether you absolutely must prevent the dictionary from being updated (e.g., for security reasons)
    or you require it to be supported by `json.dumps`, you can choose either option.

        E.g.
          data = ReadonlyDict({'foo': 'bar'})
          data['baz'] = 'xyz' # raises exception
          data.update({'baz', 'xyz'}) # raises exception
          dict.update(data, {'baz': 'xyz'}) # raises exception
    """
    def __init__(self, data):
        self.__data = dict(data)

    def __getitem__(self, key: K) -> T:
        return self.__data[key]

    def __len__(self):
        return len(self.__data)

    def __iter__(self):
        return iter(self.__data)

class StackMap(MutableMapping[K, T], typing.Generic[K, T]):
    """ A stack of mappings behaving as a single mapping, and used to implement
        nested scopes. The lookups search the stack from top to bottom, and
        returns the first value found. Mutable operations modify the topmost
        mapping only.
    """
    __slots__ = ['_maps']

    def __init__(self, m: MutableMapping[K, T] | None = None):
        self._maps = [] if m is None else [m]

    def __getitem__(self, key: K) -> T:
        for mapping in reversed(self._maps):
            try:
                return mapping[key]
            except KeyError:
                pass
        raise KeyError(key)

    def __setitem__(self, key: K, val: T):
        self._maps[-1][key] = val

    def __delitem__(self, key: K):
        del self._maps[-1][key]

    def __iter__(self) -> Iterator[K]:
        return iter({key for mapping in self._maps for key in mapping})

    def __len__(self) -> int:
        return sum(1 for key in self)

    def __str__(self) -> str:
        return f"<StackMap {self._maps}>"

    def pushmap(self, m: MutableMapping[K, T] | None = None):
        self._maps.append({} if m is None else m)

    def popmap(self) -> MutableMapping[K, T]:
        return self._maps.pop()


class OrderedSet(MutableSet[T], typing.Generic[T]):
    """ A set collection that remembers the elements first insertion order. """
    __slots__ = ['_map']

    def __init__(self, elems=()):
        self._map: dict[T, None] = dict.fromkeys(elems)

    def __contains__(self, elem):
        return elem in self._map

    def __iter__(self):
        return iter(self._map)

    def __len__(self):
        return len(self._map)

    def add(self, elem):
        self._map[elem] = None

    def discard(self, elem):
        self._map.pop(elem, None)

    def update(self, elems):
        self._map.update(zip(elems, itertools.repeat(None)))

    def difference_update(self, elems):
        for elem in elems:
            self.discard(elem)

    def __repr__(self):
        return f'{type(self).__name__}({list(self)!r})'

    def intersection(self, *others):
        return reduce(OrderedSet.__and__, others, self)


class LastOrderedSet(OrderedSet[T], typing.Generic[T]):
    """ A set collection that remembers the elements last insertion order. """
    def add(self, elem):
        self.discard(elem)
        super().add(elem)


class ConstantMapping(Mapping[typing.Any, T], typing.Generic[T]):
    """
    An immutable mapping returning the provided value for every single key.

    Useful for default value to methods
    """
    __slots__ = ['_value']

    def __init__(self, val: T):
        self._value = val

    def __len__(self):
        """
        defaultdict updates its length for each individually requested key, is
        that really useful?
        """
        return 0

    def __iter__(self):
        """
        same as len, defaultdict updates its iterable keyset with each key
        requested, is there a point for this?
        """
        return iter([])

    def __getitem__(self, item) -> T:
        return self._value