#!/usr/bin/env python
"""Single logger instance with logging to console and buffer
console log has two levels logging.INFO (default) for user messages and logging.DEBUG for debug messages
buffer log level is set to logging.DEBUG, logs are stored in stream and can be accessed with get_buffer_contents()
"""

import io
import logging
import os
import platform
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from libfb.py import everpaste
from neteng.security.lab.fixmylabdevice import osname

# Single logger instance that will be re-used
_LOGGER = logging.getLogger("fixmylabdevice")
# Logger should allow defined logging levels, handlers may set different levels
_LOGGER.setLevel(logging.DEBUG)

# Track if logger has been setup
_LOG_SETUP = False

# User facing message format, message only
_FORMATTER_USER = logging.Formatter("%(message)s")
# Debug message format
_FORMATTER_DEBUG = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# Default console log level
_CONSOLE_LEVEL = logging.INFO
# Default console message format, message only
_CONSOLE_FORMAT = _FORMATTER_USER

_APP_ID = "2647891982183725"
_APP_TOKEN = "AeP-kpjEgo3FCGwQ2b0"

if osname.is_linux() or osname.is_mac():
    _LOG_DIR = "/var/tmp"
elif osname.is_windows():
    _LOG_DIR = "/var/log"


def get_logger() -> logging.Logger:
    """Setup logger or return logger if already setup"""
    global _LOGGER, _LOG_SETUP
    if not _LOG_SETUP:
        _LOGGER.addHandler(setup_console_handler())
        _LOGGER.addHandler(setup_buffer_handler())
        _LOG_SETUP = True
    return _LOGGER


def setup_console_handler() -> logging.Handler:
    """Setup console handler"""
    handler = logging.StreamHandler()
    handler.name = "console"
    handler.setFormatter(_CONSOLE_FORMAT)
    handler.setLevel(_CONSOLE_LEVEL)
    return handler


def setup_buffer_handler() -> logging.Handler:
    """Setup buffer handler"""
    handler = logging.StreamHandler(io.StringIO())
    handler.name = "buffer"
    handler.setFormatter(_FORMATTER_DEBUG)
    handler.setLevel(logging.DEBUG)
    return handler


def get_buffer_contents() -> str:
    """Return contents of buffer log"""
    for handler in get_logger().handlers:
        if handler.name == "buffer" and isinstance(handler, logging.StreamHandler):
            contents = handler.stream.getvalue()
            return contents
    # Buffer should have been found and returned
    raise BufferError


def _set_console_handler(level: int, formatter: logging.Formatter) -> None:
    """Helper function to set level and formatter of console log when logging is already setup
    May not be thread safe, but not relevant for our use case
    """
    if _LOG_SETUP:
        for handler in get_logger().handlers:
            if handler.name == "console":
                handler.setLevel(level)
                handler.setFormatter(formatter)


def enable_debug() -> None:
    """Set debug level and formatter for console logging"""
    global _CONSOLE_LEVEL, _CONSOLE_FORMAT
    _CONSOLE_LEVEL = logging.DEBUG
    _CONSOLE_FORMAT = _FORMATTER_DEBUG
    _set_console_handler(_CONSOLE_LEVEL, _CONSOLE_FORMAT)


def disable_debug() -> None:
    """Set info level and formatter for console logging"""
    global _CONSOLE_LEVEL, _CONSOLE_FORMAT
    _CONSOLE_LEVEL = logging.INFO
    _CONSOLE_FORMAT = _FORMATTER_USER
    _set_console_handler(_CONSOLE_LEVEL, _CONSOLE_FORMAT)


def get_tempdir() -> str:
    """Get path of OS specific system temp dir"""
    # tempfile.gettempdir matches TMPDIR/TEMP/TMP env first, so we remove them
    environ_bak = {
        k: os.environ.pop(k) for k in ("TMPDIR", "TEMP", "TMP") if k in os.environ
    }
    # Now tempfile.gettempdir should get OS specific system temp dir
    tempdir = tempfile.gettempdir()
    # Restore the env variable key,values we removed
    os.environ.update(environ_bak)
    return tempdir


def get_logdir() -> Union[Path, str]:
    """Get path to logdir, create dir if it does not exist
    Very cautious to ensure logs are stored,
    as they are in important in assessing code after deployment
    """
    LOG = get_logger()
    use_tempdir = False
    syslogdir = Path(_LOG_DIR)
    logdir = syslogdir

    if not logdir.is_dir():
        # Log dir path is not directory
        LOG.debug(f"Log directory {logdir} is not directory")

        if logdir.exists():
            # Log dir path exists, could be file, link, other non-directory file system obj
            LOG.error(f"Log directory {logdir} exists and is not directory")
            use_tempdir = True

        else:
            # Log dir path does not exist
            LOG.debug(f"Log directory {logdir} does not exist. Creating it")

            try:
                # Try creating log dir path, including parents directories
                os.makedirs(logdir)

            except PermissionError:
                # Insufficient permissions to create log dir path, use temp dir
                LOG.info(
                    f"Log directory {logdir} does not exist. Insufficient permissions to create it"
                )
                use_tempdir = True

            else:
                # Log dir path was created successfully
                # Let user handle permissions, since difficult to set correct permissions/ownership
                # Since we created dir path, permissions as-is should allow creating file in it
                LOG.warning(f"Please verify permissions of {logdir} are correct")

    # test if we can write file to logdir
    testfile = f"{logdir}/fmld.testfile"
    if use_tempdir or not write_testfile(testfile):
        logdir = get_tempdir()
        LOG.debug(f"Logging to temporary log directory {logdir}")
        if not write_testfile(testfile):
            LOG.error(
                "Failed to write log file: Failed to write to {syslogdir} and {logdir}"
            )

    return logdir


def write_testfile(testfile_path: str) -> bool:
    LOG = get_logger()
    try:
        # Try writing and removing test file in log dir
        with open(testfile_path, "w") as f:
            f.write("Test writing to file")
        try:
            os.remove(testfile_path)
        except FileNotFoundError:
            # Test file some how not found, that's great!
            pass
    except IOError:
        # Failed to write test file in log dir, use temp dir
        LOG.debug(f"Failed to writing {testfile_path}")
        return False
    return True


def make_logfile() -> str:
    """Makes empty file to write log to"""
    # timestamp = datetime.now().strftime("%Y%m%d.%H%M.%f")
    # Changed from microseconds to seconds reduce filename length
    timestamp = datetime.now().strftime("%Y%m%d.%H%M%S")
    suffix = f".{timestamp}.out"
    prefix = "fmld."
    tmpdir = get_logdir()

    # Override mkstemp random string generation and use hostname instead
    tempfile._get_candidate_names = lambda: iter([platform.node()])

    _, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=tmpdir)
    return path


def buffer_to_logfile(path: Optional[str] = None) -> Optional[str]:
    """Output log buffer to file in system temp dir or to provided path"""
    LOG = get_logger()

    if not path:
        path = make_logfile()

    try:
        with open(path, "w") as f:
            f.write(get_buffer_contents())
        return path
    except IOError as e:
        LOG.exception(e)
        LOG.error(f"Failed to write log file: {path}")


def add_cacert_paths():
    """The everpaste module we use to create a paste only considers Meta provided CA certs, which lab machines do not have. Instead, we use the CA certs shipped with Linux/Mac and the CA certs provided by Prod Chef for Windows. These paths can be found in OS documentation or in the output from running the command `curl -v https://www.somesite.com`"""
    cacert_paths = (
        # Fedora/CentOS - see man update-ca-trust
        "/etc/pki/tls/certs/ca-bundle.crt",
        # MacOS
        "/etc/ssl/cert.pem",
        # Ubuntu/Debian - see man update-ca-certificates
        "/etc/ssl/certs/ca-certificates.crt",
        # Windows
        "/opscode/chef/embedded/ssl/certs/cacert.pem",
    )
    if not os.path.isfile(everpaste._CA_BUNDLE):
        for path in cacert_paths:
            if os.path.isfile(path):
                everpaste._CA_BUNDLE = path
                break


def create_paste(content: str, permanent=False, color=False) -> Optional[str]:
    LOG = get_logger()
    try:
        add_cacert_paths()
        paste = everpaste.EverPaste(_APP_ID, _APP_TOKEN)
        link = paste.create(content, permanent, color)
        return link
    except Exception as e:
        LOG.debug(f"Failed to create paste: {e}")


def buffer_log_to_paste():
    """Create paste of buffer log contents"""
    contents = get_buffer_contents()
    if contents:
        return create_paste(contents)