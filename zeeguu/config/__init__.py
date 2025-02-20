from os import getenv, path

ZEEGUU_RESOURCES_FOLDER = getenv("ZEEGUU_RESOURCES_FOLDER") or path.expanduser("~")
