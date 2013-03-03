"""
    Timer
    ~~~~~

    A simple class to measure execution time and do some calculations.
    You can use it in-memory or shared using a redis-server.

    :copyright: Michael Mayr <michael@michfrm.net>
    :licence: MIT License
"""

from __future__ import print_function, division

import time
from contextlib import contextmanager
from collections import defaultdict, deque

try:
    from blinker import signal

    # A signal which will be called any time a times block returns.
    # Call signature: (Timer, ident, start, end)
    timer_end = signal("Timer.timer_end")
except ImportError:
    timer_end = None


InMemoryBackend = lambda limit: defaultdict(lambda: deque(maxlen=limit))
InMemoryBackend.__doc__ = "In-memory storage for time measurements"


class RedisBackendItem(object):
    def __init__(self, redis, key, limit):
        self.redis = redis
        self.key = key
        self.limit = limit

    def __len__(self):
        return self.redis.llen(self.key)

    def __iter__(self):
        for value in self.redis.lrange(self.key, 0, -1):
            yield float(value)

    def append(self, value):
        self.redis.lpush(self.key, str(value))
        self.redis.ltrim(self.key, 0, self.limit - 1)


class RedisBackend(dict):
    """Redis based backend to store time measurements.
    Allows you to share timers between multiple python processes or display
    measurements on a dashboard.
    """
    def __init__(self, redis, prefix='', limit=100):
        self.redis = redis
        self.prefix = prefix
        self.limit = limit

    def __contains__(self, key):
        return self.redis.exists(self.prefix + key)

    def __getitem__(self, key):
        return RedisBackendItem(self.redis, self.prefix + key, self.limit)


class Timer(object):
    """This class creates context managers to measure the execution time
    of code blocks and provides some convenience methode like sum, avg
    or a simple estimation how long a task may take to completition.
    """

    def __init__(self, backend=InMemoryBackend):
        """Initialize timer data structures.

        :param backend: defaultdict-like object to store and receive results.
        """
        self.measures = backend

    def __call__(self, ident, method=time.time):
        """Create a new context manager to measure time.

        :param ident:  Identifier of this timer. Ident should be unique for a
                       code block you measure, otherwise you will get
                       useless results.
        :param method: Function to measure time. Defaults to time.time,
                       but you could other methods like time.clock.

        >>> t = Time()
        >>> with t("Timer 1"):
        >>>    time.sleep(1)
        """
        @contextmanager
        def context():
            """Measures time"""
            start = method()
            yield
            end = method()
            self.measures[ident].append(end - start)
            if timer_end:
                timer_end.send(self, ident, start, end)

        return context()

    def getavg(self, ident):
        """Get the average of all samples for `ident` or 0.0 if nothing
        was recorded yet"""
        if ident not in self.measures or len(self.measures[ident]) == 0:
            return 0.0
        return sum(self.measures[ident]) / len(self.measures[ident])

    def getsum(self, ident):
        """Get the sum of all samples for `ident` or 0.0 if nothing
        was recorded yet"""
        if ident not in self.measures or len(self.measures[ident]) == 0:
            return 0.0
        return sum(self.measures[ident])

    def get_time_estimate(self, ident, actions):
        """Get an estimate how long a job will still running.
        Returns None if no result can be computed.

        ident           Name of timer
        actions_left    Number of "actions" are left for this timer to complete

        """
        if ident not in self.measures or len(self.measures[ident]) == 0:
            return None
        return self.getavg(ident) * actions


def main():
    """Do some simple tests"""
    from redis import StrictRedis

    timer = Timer(backend=RedisBackend(StrictRedis()))
    for i in range(10):
        with timer("One_clock", method=time.clock):
            _ = 2 ** 2 ** 25
        with timer("One_time"):
            _ = 2 ** 2 ** 25
            print(timer.get_time_estimate("One_time", 10 - i))

    print("Clock:", timer.getsum('One_clock'), timer.getavg('One_clock'))
    print("Time:", timer.getsum('One_time'), timer.getavg('One_time'))

if __name__ == '__main__':
    main()
