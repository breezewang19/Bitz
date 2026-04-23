# Terminal ASCII Beautification Research

## Overview

This document covers techniques and Python libraries for beautifying terminal UIs using ASCII art, Unicode decorations, and ANSI colors.

---

## 1. ASCII Box Drawing

### Unicode Box Drawing Characters

```
Single-line box:
┌ ─ ┐ │ └ ┘ ├ ┤ ┬ ┴ ┼
├ ─ ─ ┤ │ │ └ ┘

Double-line box:
╔ ═ ╗ ║ ╚ ╝ ╠ ╣ ╦ ╩ ╬
╠ ═ ═ ╣ ║ ║ ╚ ╝

Block elements:
█ █ ▀ ▄ ▌ ▐ ▪ ▫
░ ▒ ▓
```

### Usage in Python

```python
# Simple box
box = """
┌────────────────────┐
│   Hello, World!    │
└────────────────────┘
"""

# With f-strings for dynamic content
width = 40
print(f"┌{'─' * width}┐")
print(f"│{' ' * width}│")
print(f"│   {'Centered Text':^30}   │")
print(f"└{'─' * width}┘")
```

---

## 2. Unicode Decorations & Symbols

### Common Symbols

```
Arrows:    → ← ↑ ↓ ↔ ↕ ➔ ➜ ➤ ➢ ➣ ➤
Bullets:   ● ○ ◉ ◎ ◆ ◇ ★ ☆ ✦ ✧
Checks:    ✓ ✔ ✗ ✘ ☑ ☒
Shapes:    ▲ △ ▼ ▽ ● ○ ■ □ ◆ ◇
Misc:      ♠ ♣ ♥ ♦ ★ ◆ ● ■ ▪
Lines:     ─ │ ┌ ┐ └ ┘ ├ ┤ ┬ ┴ ┼
```

### In Python

```python
print("● Option 1")
print("○ Option 2")
print("✓ Success")
print("✗ Error")
print("→ Next step")
```

---

## 3. Progress Indicators

### ASCII Spinners

```python
import time

spinners = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

for frame in range(50):
    i = frame % len(spinners)
    print(f"\r{spinners[i]} Loading...", end="", flush=True)
    time.sleep(0.1)

# Block progress bar
def progress_bar(current, total, width=40):
    percent = current / total
    filled = int(width * percent)
    bar = '█' * filled + '░' * (width - filled)
    return f"[{bar}] {percent*100:.1f}%"

print(progress_bar(65, 100))  # [████████████████░░░░░░░░░░░░░░░░] 65.0%
```

---

## 4. Table Formatting

### Manual ASCII Table

```python
def print_table(headers, rows):
    col_widths = [max(len(str(cell)) for cell in col) for col in zip(headers, *rows)]
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    
    print(separator)
    print("|" + "|".join(f" {h:^{w}} " for h, w in zip(headers, col_widths)) + "|")
    print(separator.replace("-", "="))
    for row in rows:
        print("|" + "|".join(f" {c:{w}} " for c, w in zip(row, col_widths)) + "|")
        print(separator)
```

---

## 5. ANSI Color Schemes

### Basic ANSI Colors

```
Reset:        \033[0m
Bold:         \033[1m
Dim:          \033[2m
Italic:       \033[3m
Underline:    \033[4m

Foreground:
  Black:      \033[30m  Red:        \033[31m  Green:    \033[32m
  Yellow:     \033[33m  Blue:       \033[34m  Magenta:  \033[35m
  Cyan:      \033[36m  White:      \033[37m

Background:
  Black:      \033[40m  Red:        \033[41m  Green:    \033[42m
  Yellow:    \033[43m  Blue:       \033[44m  Magenta:  \033[45m
  Cyan:      \033[46m  White:      \033[47m
```

### Python Helper Class

```python
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    
    @classmethod
    def color(cls, text, color_code):
        return f"{color_code}{text}{cls.RESET}"
    
    @classmethod
    def red(cls, text):
        return cls.color(text, cls.RED)
    
    @classmethod
    def green(cls, text):
        return cls.color(text, cls.GREEN)
    
    @classmethod
    def bold(cls, text):
        return cls.color(text, cls.BOLD)

# Usage
print(f"{Colors.red('Error!')} Something went wrong")
print(f"{Colors.green('Success!')} Operation complete")
print(f"{Colors.bold(Colors.yellow('Warning!'))} Check your input")
```

### 256-Color Mode

```python
# 256-color foreground: \033[38;5;Nm where N is 0-255
# 256-color background: \033[48;5;Nm

# Example: color 214 (orange)
print("\033[38;5;214mOrange text\033[0m")

# True color (24-bit RGB)
print("\033[38;2;255;127;0mTrue orange\033[0m")
```

---

## 6. Python Libraries

### rich — Rich Text and Beautiful Formatting

**What it does:** The most popular library for rich terminal output. Supports colorful text, tables, progress bars, syntax highlighting, markdown, and more. Very high-level API.

**Installation:**
```bash
pip install rich
```

**Examples:**

```python
from rich.console import Console
from rich.table import Table
from rich.progress import track
import time

console = Console()

# Colorful text
console.print("[bold magenta]Hello[/bold magenta] [green]World![/green]")

# Table
table = Table(show_header=True)
table.add_column("Name", style="cyan")
table.add_column("Age", justify="right", style="yellow")
table.add_column("Status", style="bold green")

table.add_row("Alice", "30", "Active")
table.add_row("Bob", "25", "Inactive")
table.add_row("Charlie", "35", "[bold]Active[/bold]")
console.print(table)

# Progress bar
for i in track(range(100), description="Processing..."):
    time.sleep(0.01)

# Live display
with console.status("[bold green]Working...") as status:
    time.sleep(2)
    console.print("[cyan]Done![/cyan]")
```

**Strengths:** Extremely feature-rich, excellent documentation, drop-in `print` replacement via `from rich import print`. Very popular (22k+ stars).

**Best for:** Quick beautification of existing CLI tools, progress bars, tables, markdown rendering.

---

### blessed — Terminal Interface Library

**What it does:** Provides an elegant, high-level interface to Colors, Keyboard input, and screen positioning. Handles terminal capabilities via terminfo. Great for TUI applications with keyboard/mouse interaction.

**Installation:**
```bash
pip install blessed
```

**Examples:**

```python
from blessed import Terminal

term = Terminal()

# Colors and styling
print(term.bold('Bold text'))
print(term.red('Error message'))
print(term.green_on_black('Success!'))

# Positioning
with term.location(x=10, y=5):
    print('Text at position 10,5')

# Clear screen
print(term.clear)

# Full-screen application
with term.fullscreen():
    with term.cbreak():
        key = term.inkey()
        if key == 'q':
            break

# Key handling
with term.cbreak():
    key = term.inkey()
    if key.name == 'KEY_UP':
        print('Pressed UP')
```

**Strengths:** Excellent for cursor positioning, keyboard/mouse handling, works with any terminal. Well-documented with many examples.

**Best for:** Interactive TUIs, games, menus, any application needing keyboard/mouse input.

---

### texttable — Simple ASCII Tables

**What it does:** Lightweight library specifically for creating ASCII tables. Simple API for bordered tables with alignment and styling.

**Installation:**
```bash
pip install texttable
```

**Examples:**

```python
from texttable import Texttable

table = Texttable()
table.set_cols_align(["l", "r", "c"])  # left, right, center
table.set_cols_valign(["t", "m", "b"])  # top, middle, bottom
table.set_deco(Texttable.HEADER | Texttable.BORDER)
table.add_rows([
    ["Name", "Age", "Score"],
    ["Alice", 30, 95],
    ["Bob", 25, 87],
    ["Charlie", 35, 92]
])
print(table.draw())

# Output:
# +------+-----+-------+
# | Name | Age | Score |
# +======+=====+=======+
# | Alice |  30 |   95  |
# | Bob   |  25 |   87  |
# |Charlie|  35 |   92  |
# +------+-----+-------+
```

**Strengths:** Lightweight, simple API, supports Unicode via wcwidth.

**Best for:** Quick simple tables without heavy dependencies.

---

### terminaltables — ASCII Tables with Styles

**What it does:** Generates plain ASCII tables in various styles (ASCII, Single, Double). Lightweight and dependency-free.

**Installation:**
```bash
pip install terminaltables
```

**Examples:**

```python
from terminaltables import AsciiTable, SingleTable, DoubleTable

table_data = [
    ['Name', 'Version', 'Status'],
    ['Alice', '1.0', 'Active'],
    ['Bob', '2.1', 'Inactive']
]

# Different styles
print(AsciiTable(table_data).table)
print(SingleTable(table_data).table)
print(DoubleTable(table_data).table)

# With title
table = SingleTable(table_data, title="Users")
table.justify_columns[2] = 'right'
print(table.table)
```

**Strengths:** Multiple table styles, title support, alignment options, no dependencies.

**Best for:** Simple table display with multiple style options.

---

### beautifultable — Feature-Rich ASCII Tables

**What it does:** Printing visually appealing ASCII tables with full customization, color support via ANSI or other libraries, and predefined styles.

**Installation:**
```bash
pip install beautifultable
```

**Examples:**

```python
from beautifultable import BeautifulTable

table = BeautifulTable()
table.column_headers = ['Name', 'Age', 'City']

# Row by row
table.append_row(['Alice', 30, 'New York'])
table.append_row(['Bob', 25, 'London'])

# Or initialize from iterable
table = BeautifulTable()
table.set_rows([
    ['Alice', 30, 'New York'],
    ['Bob', 25, 'London'],
])
table.max_width = 60

print(table)

# Custom styles
from beautifultable import BORDER_STYLE_COMPACT
table = BeautifulTable(cwd=0, border_style=BORDER_STYLE_COMPACT)
```

**Strengths:** Very customizable, color support, Unicode-aware, multiple border styles, iterates by row or column.

**Best for:** Complex tables needing full control over appearance.

---

### tqdm — Progress Bars

**What it does:** Fast, extensible progress bar library. Wraps any iterable with a progress meter. Used heavily in ML/data science.

**Installation:**
```bash
pip install tqdm
```

**Examples:**

```python
from tqdm import tqdm
import time

# Basic usage
for i in tqdm(range(100)):
    time.sleep(0.01)

# Manual update
with tqdm(total=100) as pbar:
    for i in range(10):
        time.sleep(0.1)
        pbar.update(10)

# Description
pbar = tqdm(range(100), desc="Processing")
for item in pbar:
    pbar.set_description(f"Item {item}")
    time.sleep(0.01)

# Alternative: trange
from tqdm import trange
for i in trange(100):
    time.sleep(0.01)
```

**Strengths:** Minimal overhead, smart algorithms for remaining time prediction, works in Jupyter, many customization options.

**Best for:** Long-running operations needing progress indication.

---

### asciimatics — Animations and Games

**What it does:** Full framework for creating ASCII animations, games, and interactive TUI applications. Includes sprites, scenes, and user input handling.

**Installation:**
```bash
pip install asciimatics
```

**Examples:**

```python
from asciimatics.screen import Screen
from asciimatics.effects import Print
from asciimatics.renderers import FigletText

def demo(screen):
    # Print figlet text
    screen.print_at(FigletText("Hello", width=screen.width), 0, 0)
    screen.refresh()

Screen.wrapper(demo)

# Animation effect
from asciimatics.effects import Cycle, Stars

def demo(screen):
    effects = [
        Stars(screen, 200),
        Cycle(screen, FigletText("ASCII!", width=screen.width), y=10)
    ]
    screen.play(effects, sprite_cycles=True)

Screen.wrapper(demo)
```

**Strengths:** Complete animation framework, sprites, scenes, collision detection, high-level API for games.

**Best for:** ASCII games, visual effects, animated demos.

---

### blessings — Terminal Formatting (lightweight)

**What it does:** Provides a simple, elegant API for colors and formatting without the overhead of curses. Cleaner interface than blessed for basic use.

**Installation:**
```bash
pip install blessings
```

**Examples:**

```python
from blessings import Terminal

t = Terminal()

# Simple color
print(t.red('Error!'))
print(t.green('Success!'))

# Styling
print(t.bold(t.underline('Important!')))
print(t.red_on_white('Alert!'))

# Positioning
with t.move(10, 20):
    print('At row 10, col 20')

# Fullscreen mode
with t.fullscreen():
    print(t.center('Centered!'))
```

**Strengths:** Very lightweight, simple API, chainable styles.

**Best for:** Simple terminal formatting without full TUI complexity.

---

## 7. Inspiration: Well-Designed TUIs

### htop
- Uses ncurses for interactive display
- Color-coded meters (green/yellow/red based on load)
- Real-time updating bars
- Interactive process selection

### neofetch
- ASCII art logo display
- Info boxes aligned with borders
- Color gradient themes
- Shows system info in columns

### Other notable TUIs:
- **btop** — Modern, colorful, box-drawn meters
- **glances** — Multi-threaded status display
- **midnight commander** — Classic dual-pane file manager
- **vim** — Modal editing with status lines

### Design Patterns to Emulate

```python
# Box with info panel (like neofetch)
def neofetch_style():
    logo = """
    ███╗   ██╗██████╗ ██╗██╗  ██╗ █████╗ 
    ████╗  ██║██╔══██╗██║╚██╗██╔╝██╔══██╗
    ██╔██╗ ██║██████╔╝██║ ╚███╔╝ ███████║
    ██║╚██╗██║██╔═══╝ ██║ ██╔██╗ ██╔══██║
    ██║ ╚████║██║     ██║██╔╝ ██╗██║  ██║
    ╚═╝  ╚═══╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝
    """
    
    info = """
    OS:       Ubuntu 24.04 LTS
    Host:     my-computer
    Kernel:   6.8.0-45-generic
    Shell:    zsh 5.9
    """
    
    print(logo)
    print(info)

# Progress meters (like htop)
def htop_style_meter():
    def meter(value, max_val, width=20, color='green'):
        filled = int(width * (value / max_val))
        colors = {'green': '\033[92m', 'yellow': '\033[93m', 'red': '\033[91m'}
        reset = '\033[0m'
        bar = colors[color] + '█' * filled + '░' * (width - filled) + reset
        return f"[{bar}] {value}/{max_val}"
    
    print(f"CPU:    {meter(65, 100)}")
    print(f"Memory: {meter(45, 100)}")
    print(f"Disk:   {meter(80, 100)}")
```

---

## 8. Quick Integration Checklist

For adding beautification to an existing Python TUI:

1. **Start simple**: Use ANSI color codes directly for text coloring
2. **Tables**: Add `texttable` or `beautifultable` for tabular data
3. **Progress**: Add `tqdm` wrapping for loops
4. **Rich text**: Replace `print()` with `rich.print()` for styled output
5. **Interactive**: Use `blessed` for cursor positioning and keyboard input

### Minimal Dependencies Approach

```python
# Color helper (no dependencies)
class C:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"

print(f"{C.BOLD}{C.RED}Error: {C.RESET}Something went wrong")
print(f"{C.GREEN}Success!{C.RESET}")
```

---

## 9. Resources

- ANSI escape codes: https://ansi.tools/
- Rich library: https://github.com/textualize/rich
- Blessed library: https://github.com/jquast/blessed
- Unicode box drawing reference: Various Unicode blocks (Box Drawing U+2500-U+257F)
