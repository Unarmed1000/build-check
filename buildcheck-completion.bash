#!/usr/bin/env bash
# ****************************************************************************************************************************************************
# * BSD 3-Clause License
# *
# * Copyright (c) 2025, Mana Battery
# * All rights reserved.
# *
# * Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
# *
# * 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
# * 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the
# *    documentation and/or other materials provided with the distribution.
# * 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this
# *    software without specific prior written permission.
# *
# * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# * THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# * PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# * LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
# * EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# ****************************************************************************************************************************************************

# Bash completion script for buildCheck tools
#
# Installation:
#   1. Source this file in your ~/.bashrc:
#      source /path/to/buildcheck-completion.bash
#
#   2. Or copy to system completion directory:
#      sudo cp buildcheck-completion.bash /etc/bash_completion.d/buildcheck
#
# Usage:
#   buildCheckSummary <TAB>
#   buildCheckDSM --<TAB>
#   etc.

# Helper function to complete directory paths
_buildcheck_dir_completion() {
    local cur="${1}"
    compgen -d -- "${cur}"
}

# Helper function to complete file paths
_buildcheck_file_completion() {
    local cur="${1}"
    compgen -f -- "${cur}"
}

# buildCheckSummary completion
_buildCheckSummary() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="--detailed --format --output -o --no-color --verbose -v --version --help -h"

    case "${prev}" in
        --format)
            COMPREPLY=( $(compgen -W "text json" -- "${cur}") )
            return 0
            ;;
        --output|-o)
            COMPREPLY=( $(_buildcheck_file_completion "${cur}") )
            return 0
            ;;
        buildCheckSummary|buildCheckSummary.py)
            COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
            return 0
            ;;
    esac

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
}

# buildCheckDSM completion
_buildCheckDSM() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="--version --top --cycles-only --show-layers --export --export-graph --filter --exclude
          --cluster-by-directory --show-library-boundaries --library-filter --cross-library-only
          --verbose --file-scope --sort-by --compare-with --save-results --load-baseline
          --git-impact --git-from --git-repo --suggest-improvements --sensitivity --help -h"

    case "${prev}" in
        --export|--export-graph|--save-results|--load-baseline)
            COMPREPLY=( $(_buildcheck_file_completion "${cur}") )
            return 0
            ;;
        --compare-with|--git-repo)
            COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
            return 0
            ;;
        --sort-by)
            COMPREPLY=( $(compgen -W "coupling topological" -- "${cur}") )
            return 0
            ;;
        --file-scope)
            COMPREPLY=( $(compgen -W "project thirdparty system" -- "${cur}") )
            return 0
            ;;
        --sensitivity)
            COMPREPLY=( $(compgen -W "low medium high" -- "${cur}") )
            return 0
            ;;
        --filter|--exclude|--library-filter|--top|--git-from)
            # Let user type freely
            return 0
            ;;
        buildCheckDSM|buildCheckDSM.py)
            COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
            return 0
            ;;
    esac

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
}

# buildCheckIncludeChains completion
_buildCheckIncludeChains() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="--threshold --max-results --verbose -v --version --help -h"

    case "${prev}" in
        --threshold|--max-results)
            # Let user type number
            return 0
            ;;
        buildCheckIncludeChains|buildCheckIncludeChains.py)
            COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
            return 0
            ;;
    esac

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
}

# buildCheckDependencyHell completion
_buildCheckDependencyHell() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="--threshold --top --detailed --changed --exclude --include-system-headers 
          --verbose -v --version --help -h"

    case "${prev}" in
        --threshold|--top)
            # Let user type number
            return 0
            ;;
        --exclude)
            # Let user type pattern
            return 0
            ;;
        buildCheckDependencyHell|buildCheckDependencyHell.py)
            COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
            return 0
            ;;
    esac

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
}

# buildCheckRippleEffect completion
_buildCheckRippleEffect() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="--repo --from --json --verbose -v --log-level --include-system-headers --version --help -h"

    case "${prev}" in
        --repo)
            COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
            return 0
            ;;
        --from)
            # Let user type git reference
            return 0
            ;;
        --json)
            COMPREPLY=( $(_buildcheck_file_completion "${cur}") )
            return 0
            ;;
        --log-level)
            COMPREPLY=( $(compgen -W "DEBUG INFO WARNING ERROR CRITICAL" -- "${cur}") )
            return 0
            ;;
        buildCheckRippleEffect|buildCheckRippleEffect.py)
            COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
            return 0
            ;;
    esac

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
}

# buildCheckLibraryGraph completion
_buildCheckLibraryGraph() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="--top --libs-only --find-dependents --impacted-by --export --cycles-only 
          --verbose -v --version --help -h"

    case "${prev}" in
        --top)
            # Let user type number
            return 0
            ;;
        --find-dependents|--impacted-by)
            # Let user type library name
            return 0
            ;;
        --export)
            COMPREPLY=( $(_buildcheck_file_completion "${cur}") )
            return 0
            ;;
        buildCheckLibraryGraph|buildCheckLibraryGraph.py)
            COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
            return 0
            ;;
    esac

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
}

# buildCheckImpact completion
_buildCheckImpact() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="--all-headers --verbose -v --limit --version --help -h"

    case "${prev}" in
        --limit)
            # Let user type number
            return 0
            ;;
        buildCheckImpact|buildCheckImpact.py)
            COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
            return 0
            ;;
    esac

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
}

# buildCheckIncludeGraph completion
_buildCheckIncludeGraph() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="--top --full --verbose --include-system-headers --version --help -h"

    case "${prev}" in
        --top)
            # Let user type number
            return 0
            ;;
        buildCheckIncludeGraph|buildCheckIncludeGraph.py)
            COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
            return 0
            ;;
    esac

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
}

# buildCheckOptimize completion
_buildCheckOptimize() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="--quick --focus --top --report --min-impact --exclude --verbose -v 
          --version --help -h"

    case "${prev}" in
        --top|--min-impact)
            # Let user type number
            return 0
            ;;
        --report)
            COMPREPLY=( $(_buildcheck_file_completion "${cur}") )
            return 0
            ;;
        --focus)
            COMPREPLY=( $(compgen -W "libraries headers cycles architecture build-system all" -- "${cur}") )
            return 0
            ;;
        --exclude)
            # Let user type pattern
            return 0
            ;;
        buildCheckOptimize|buildCheckOptimize.py)
            COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
            return 0
            ;;
    esac

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    COMPREPLY=( $(_buildcheck_dir_completion "${cur}") )
}

# Register completion functions for all buildCheck scripts
complete -F _buildCheckSummary buildCheckSummary buildCheckSummary.py
complete -F _buildCheckDSM buildCheckDSM buildCheckDSM.py
complete -F _buildCheckIncludeChains buildCheckIncludeChains buildCheckIncludeChains.py
complete -F _buildCheckDependencyHell buildCheckDependencyHell buildCheckDependencyHell.py
complete -F _buildCheckRippleEffect buildCheckRippleEffect buildCheckRippleEffect.py
complete -F _buildCheckLibraryGraph buildCheckLibraryGraph buildCheckLibraryGraph.py
complete -F _buildCheckImpact buildCheckImpact buildCheckImpact.py
complete -F _buildCheckIncludeGraph buildCheckIncludeGraph buildCheckIncludeGraph.py
complete -F _buildCheckOptimize buildCheckOptimize buildCheckOptimize.py
