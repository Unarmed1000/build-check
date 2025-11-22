#!/usr/bin/env python3
"""Colorama wrapper utilities for colored terminal output."""

import sys
import os
import logging
from typing import Optional, TextIO, List, Tuple, Any

logger = logging.getLogger(__name__)

# Try to import colorama
try:
    from colorama import Fore, Style, Back, init
    init(autoreset=False)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    logger.debug("colorama not available, using fallback")


# Define color classes with fallback
if COLORAMA_AVAILABLE:
    # Use actual colorama
    class Colors:
        """Color codes for terminal output."""
        # Foreground colors
        RED = Fore.RED
        GREEN = Fore.GREEN
        YELLOW = Fore.YELLOW
        BLUE = Fore.BLUE
        MAGENTA = Fore.MAGENTA
        CYAN = Fore.CYAN
        WHITE = Fore.WHITE
        BLACK = Fore.BLACK
        
        # Styles
        RESET = Style.RESET_ALL
        BRIGHT = Style.BRIGHT
        DIM = Style.DIM
        NORMAL = Style.NORMAL
        
        # Background colors
        BG_RED = Back.RED
        BG_GREEN = Back.GREEN
        BG_YELLOW = Back.YELLOW
        BG_BLUE = Back.BLUE
        
        @staticmethod
        def disable() -> None:
            """Disable all color output."""
            for attr in dir(Colors):
                if not attr.startswith('_') and attr != 'disable':
                    setattr(Colors, attr, '')
else:
    # Fallback without colors
    class ColorsNoColor:
        """Fallback color codes (empty strings)."""
        RED = ''
        GREEN = ''
        YELLOW = ''
        BLUE = ''
        MAGENTA = ''
        CYAN = ''
        WHITE = ''
        BLACK = ''
        RESET = ''
        BRIGHT = ''
        DIM = ''
        NORMAL = ''
        BG_RED = ''
        BG_GREEN = ''
        BG_YELLOW = ''
        BG_BLUE = ''
        
        @staticmethod
        def disable() -> None:
            """No-op for fallback."""
            pass
    
    # Use the fallback class as Colors
    Colors = ColorsNoColor  # type: ignore[misc,assignment]


def colored(text: str, color: str = '', style: str = '') -> str:
    """Return colored text string.
    
    Args:
        text: Text to colorize
        color: Color code (e.g., Colors.RED)
        style: Style code (e.g., Colors.BRIGHT)
        
    Returns:
        Formatted string with color codes
    """
    if not COLORAMA_AVAILABLE or not color:
        return text
    
    return f"{style}{color}{text}{Colors.RESET}"


def print_colored(text: str, color: str = '', style: str = '', file: Optional[TextIO] = None) -> None:
    """Print colored text to file/stdout.
    
    Args:
        text: Text to print
        color: Color code
        style: Style code
        file: File object (default: sys.stdout)
    """
    if file is None:
        file = sys.stdout
    
    print(colored(text, color, style), file=file)


def print_success(text: str, file: Optional[TextIO] = None, prefix: bool = False) -> None:
    """Print success message in green.
    
    Args:
        text: Message to print
        file: File object (default: sys.stdout)
        prefix: If True, prepend "Success: " to message
    """
    message = f"Success: {text}" if prefix else text
    print_colored(message, Colors.GREEN, file=file)


def print_error(text: str, file: Optional[TextIO] = None, prefix: bool = True) -> None:
    """Print error message in red to stderr.
    
    Args:
        text: Error message to print
        file: File object (default: sys.stderr)
        prefix: If True, prepend "Error: " to message (default: True)
    """
    if file is None:
        file = sys.stderr
    message = f"Error: {text}" if prefix else text
    print_colored(message, Colors.RED, file=file)


def print_warning(text: str, file: Optional[TextIO] = None, prefix: bool = True) -> None:
    """Print warning message in yellow to stderr.
    
    Args:
        text: Warning message to print
        file: File object (default: sys.stderr)
        prefix: If True, prepend "Warning: " to message (default: True)
    """
    if file is None:
        file = sys.stderr
    message = f"Warning: {text}" if prefix else text
    print_colored(message, Colors.YELLOW, file=file)


def print_info(text: str, file: Optional[TextIO] = None) -> None:
    """Print info message in cyan."""
    print_colored(text, Colors.CYAN, file=file)


def print_highlight(text: str, file: Optional[TextIO] = None) -> None:
    """Print highlighted text in bright white."""
    print_colored(text, Colors.WHITE, Colors.BRIGHT, file=file)


def is_color_supported() -> bool:
    """Check if color output is supported.
    
    Returns:
        True if colorama is available
    """
    return COLORAMA_AVAILABLE


def should_use_color(force_color: bool = False, no_color: bool = False) -> bool:
    """Determine if color should be used based on environment and flags.
    
    Args:
        force_color: Force color output regardless of terminal
        no_color: Disable color output
        
    Returns:
        True if color should be used
    """
    if no_color:
        return False
    
    if force_color:
        return COLORAMA_AVAILABLE
    
    # Check if stdout is a TTY
    if not sys.stdout.isatty():
        return False
    
    # Check NO_COLOR environment variable (see no-color.org)
    if os.environ.get('NO_COLOR'):
        return False
    
    return COLORAMA_AVAILABLE


# Severity color mapping
SEVERITY_COLORS = {
    'critical': (Colors.RED, Colors.BRIGHT),
    'high': (Colors.RED, Colors.NORMAL),
    'moderate': (Colors.YELLOW, Colors.NORMAL),
    'low': (Colors.GREEN, Colors.NORMAL),
    'info': (Colors.CYAN, Colors.NORMAL),
}


def get_severity_color(severity: str) -> Tuple[str, str]:
    """Get color and style for a severity level.
    
    Args:
        severity: Severity level string
        
    Returns:
        Tuple of (color, style)
    """
    severity = severity.lower()
    return SEVERITY_COLORS.get(severity, (Colors.WHITE, Colors.NORMAL))


def print_severity(text: str, severity: str, file: Optional[TextIO] = None) -> None:
    """Print text with severity-appropriate coloring.
    
    Args:
        text: Text to print
        severity: Severity level (critical/high/moderate/low/info)
        file: File object (default: sys.stdout)
    """
    color, style = get_severity_color(severity)
    print_colored(text, color, style, file=file)


def format_table_row(columns: List[Any], widths: List[int], colors: Optional[List[str]] = None) -> str:
    """Format a table row with optional column colors.
    
    Args:
        columns: List of column values (strings)
        widths: List of column widths
        colors: Optional list of color codes for each column
        
    Returns:
        Formatted table row string
    """
    if colors is None:
        colors = [''] * len(columns)
    
    parts = []
    for col, width, color in zip(columns, widths, colors):
        if color:
            parts.append(colored(str(col).ljust(width), color))
        else:
            parts.append(str(col).ljust(width))
    
    return ' '.join(parts)


def progress_bar(current: int, total: int, width: int = 40, 
                 color: str = Colors.GREEN) -> str:
    """Create a colored progress bar string.
    
    Args:
        current: Current progress value
        total: Total value
        width: Width of progress bar in characters
        color: Color for filled portion
        
    Returns:
        Formatted progress bar string
    """
    if total == 0:
        percent = 0
    else:
        percent = min(100, int(100 * current / total))
    
    filled = int(width * current / total) if total > 0 else 0
    bar = '█' * filled + '░' * (width - filled)
    
    if COLORAMA_AVAILABLE and color:
        bar = f"{color}{bar}{Colors.RESET}"
    
    return f"[{bar}] {percent}%"
