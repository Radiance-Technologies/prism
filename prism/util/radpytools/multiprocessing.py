# decorators for critical sections

def critical(lock):
    def inner(f):
        def g(*args,**kwargs):
            lock.acquire()
            f(*args,**kwargs)
            lock.release()
        return g
    return inner
