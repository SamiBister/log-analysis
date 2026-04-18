"""Shell completion script emitter for logscope."""

_BASH_COMPLETION = """\
_logscope_complete() {
    local cur prev words cword
    _init_completion || return

    local subcommands="config update completions"
    local config_subcommands="show edit path"
    local global_flags="--file --model --context --max-context-bytes --redact-pii --redact-hosts --redact-ips --no-redact --show-redacted --diff --last --max-bytes -q --quiet --no-translate --version"
    local models="claude-sonnet-4-6 claude-opus-4-6 gpt-4o gpt-4.1"

    # Determine if a subcommand has already been given
    local cmd=""
    local i
    for (( i=1; i < cword; i++ )); do
        case "${words[i]}" in
            config|update|completions)
                cmd="${words[i]}"
                break
                ;;
        esac
    done

    case "$cmd" in
        config)
            local sub_cmd=""
            for (( i=2; i < cword; i++ )); do
                case "${words[i]}" in
                    show|edit|path)
                        sub_cmd="${words[i]}"
                        break
                        ;;
                esac
            done
            if [[ -z "$sub_cmd" ]]; then
                COMPREPLY=( $(compgen -W "${config_subcommands}" -- "$cur") )
            fi
            return
            ;;
        update|completions)
            return
            ;;
        *)
            case "$prev" in
                --model)
                    COMPREPLY=( $(compgen -W "${models}" -- "$cur") )
                    return
                    ;;
                --file)
                    _filedir
                    return
                    ;;
            esac
            if [[ "$cur" == -* ]]; then
                COMPREPLY=( $(compgen -W "${global_flags}" -- "$cur") )
            else
                COMPREPLY=( $(compgen -W "${subcommands}" -- "$cur") )
            fi
            ;;
    esac
}

complete -F _logscope_complete logscope
"""

_ZSH_COMPLETION = """\
#compdef logscope

_logscope() {
    local state line
    typeset -A opt_args

    local -a global_flags
    global_flags=(
        '--file[Path to log file]:file:_files'
        '--model[AI model to use]:model:(claude-sonnet-4-6 claude-opus-4-6 gpt-4o gpt-4.1)'
        '--context[Extra context to inject into the prompt]:context:'
        '--max-context-bytes[Maximum bytes for context]:bytes:'
        '--redact-pii[Redact PII before sending]'
        '--redact-hosts[Redact hostnames]'
        '--redact-ips[Redact IP addresses]'
        '--no-redact[Disable all redaction]'
        '--show-redacted[Show what was redacted]'
        '--diff[Show diff of changes]'
        '--last[Analyse last N lines]:lines:'
        '--max-bytes[Maximum bytes to read]:bytes:'
        '-q[Quiet mode — suppress non-essential output]'
        '--quiet[Quiet mode — suppress non-essential output]'
        '--no-translate[Skip translation step]'
        '--version[Show version and exit]'
    )

    _arguments -C \\
        "${global_flags[@]}" \\
        '1: :->command' \\
        '*:: :->args'

    case $state in
        command)
            local -a commands
            commands=(
                'config:Manage logscope configuration'
                'update:Check for a newer version'
                'completions:Emit shell completion script'
            )
            _describe 'command' commands
            ;;
        args)
            case $line[1] in
                config)
                    local -a config_cmds
                    config_cmds=(
                        'show:Print current configuration'
                        'edit:Open configuration in editor'
                        'path:Print path to config file'
                    )
                    _arguments '1: :->config_sub' '*:: :->config_args'
                    case $state in
                        config_sub)
                            _describe 'config subcommand' config_cmds
                            ;;
                    esac
                    ;;
            esac
            ;;
    esac
}

compdef _logscope logscope
"""


def emit(shell: str) -> str:
    """Return a shell completion script for logscope as a string.

    The script covers all top-level flags, subcommands (``config``,
    ``update``, ``completions``), ``config`` sub-subcommands
    (``show``, ``edit``, ``path``), and static ``--model`` completions.

    Args:
        shell: The target shell.  Must be ``"bash"`` or ``"zsh"``.

    Returns:
        The completion script as a plain string ready to be eval'd or
        sourced.  Source it from your shell rc file::

            # bash — add to ~/.bashrc
            eval "$(logscope completions bash)"

            # zsh — add to ~/.zshrc
            eval "$(logscope completions zsh)"

    Raises:
        ValueError: If *shell* is not ``"bash"`` or ``"zsh"``.
    """
    match shell:
        case "bash":
            return _BASH_COMPLETION
        case "zsh":
            return _ZSH_COMPLETION
        case _:
            raise ValueError(f"Unsupported shell {shell!r}. Choose 'bash' or 'zsh'.")
