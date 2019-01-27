import threading
import logging

class Context:
    def __init__(self, url):
        self.url = url

    def __enter__(self):
        set_current_url(self.url)

    def __exit__(self, exc_type, exc_val, exc_tb):
        set_current_url(None)


def url_context(url):
    return Context(url)


def set_current_url(url = None):
    thread = threading.current_thread()
    orig_name = get_original_name()

    if not url:
        if orig_name:
            thread.name = orig_name

        return

    if not orig_name:
        threading.local().orig_name = thread.name

    thread.name = url


def get_original_name():
    try:
        return threading.local().orig_name
    except AttributeError:
        return None


def get_logger(name="tracer"):
    return logging.getLogger(name)
