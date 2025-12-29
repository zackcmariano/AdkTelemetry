# oraicle/context.py

import contextvars

current_root = contextvars.ContextVar("current_root", default=None)

def set_root(agent):
    current_root.set(agent)

def get_root():
    return current_root.get()
