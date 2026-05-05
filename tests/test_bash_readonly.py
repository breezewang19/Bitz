from agent.builtin_tools import bash_is_readonly

# --- Safe commands should return True ---
def test_simple_readonly():
    assert bash_is_readonly("ls") is True
    assert bash_is_readonly("ls -la") is True
    assert bash_is_readonly("cat file.txt") is True
    assert bash_is_readonly("pwd") is True
    assert bash_is_readonly("echo hello") is True

def test_git_readonly_subcommands():
    assert bash_is_readonly("git status") is True
    assert bash_is_readonly("git log --oneline") is True
    assert bash_is_readonly("git diff") is True
    assert bash_is_readonly("git branch") is True

def test_git_with_flags():
    assert bash_is_readonly("git --version") is True
    assert bash_is_readonly("git --exec-path=/tmp status") is True

def test_npm_readonly():
    assert bash_is_readonly("npm audit") is True
    assert bash_is_readonly("npm list") is True
    assert bash_is_readonly("npm view react") is True

def test_gh_readonly():
    assert bash_is_readonly("gh pr list") is True
    assert bash_is_readonly("gh issue view 123") is True

# --- Dangerous commands should return False ---
def test_dangerous_commands():
    assert bash_is_readonly("rm -rf /") is False
    assert bash_is_readonly("npm install") is False
    assert bash_is_readonly("git push") is False

def test_compound_command_semicolon():
    assert bash_is_readonly("git status; rm -rf /") is False

def test_pipe():
    assert bash_is_readonly("ls | grep foo") is False

def test_redirect():
    assert bash_is_readonly("echo hello > file.txt") is False

def test_command_substitution():
    assert bash_is_readonly("echo $(whoami)") is False

def test_backtick():
    assert bash_is_readonly("echo `whoami`") is False

def test_quoted_semicolon_is_safe():
    assert bash_is_readonly('echo "hello; world"') is True

def test_empty_command():
    assert bash_is_readonly("") is True

def test_unknown_command():
    assert bash_is_readonly("python3 -c 'print(1)'") is False

def test_git_no_subcommand():
    assert bash_is_readonly("git") is False

def test_npm_no_subcommand():
    assert bash_is_readonly("npm") is False
