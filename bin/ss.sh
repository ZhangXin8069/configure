#!/usr/bin/env bash
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"

_usage() {
    echo "用法: ss [缩写|数字|缩写数字组合]" >&2
    echo "缩写: k, z, x, zx, y, ht, yht" >&2
}

_finish() {
    echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
    exit "${1:-0}"
}

main() {
    local short alias ip_text ip user default_ip numeric_fallback_user rc

    numeric_fallback_user="zhangxin"

    if (( $# > 1 )); then
        echo "ss: 只接受一个缩写、数字或组合参数" >&2
        _usage
        _finish 64
    fi

    short=${1:-k}
    short=$(printf '%s' "${short}" | tr '[:upper:]' '[:lower:]')
    if [[ ! "${short}" =~ ^([a-z]*)([0-9]{0,3})([a-z]*)$ ]]; then
        echo "ss: 不支持的目标: ${1:-}" >&2
        _usage
        _finish 64
    fi

    alias="${BASH_REMATCH[1]}${BASH_REMATCH[3]}"
    ip_text="${BASH_REMATCH[2]}"

    case "${alias}" in
        k) user="kfutfd"; default_ip=19 ;;
        z) user="zhang"; default_ip=3 ;;
        x) user="xin"; default_ip=4 ;;
        zx) user="zhangxin"; default_ip=2 ;;
        y) user="yang"; default_ip=11 ;;
        ht) user="haotian"; default_ip=12 ;;
        yht|yh) user="yanghaotian"; default_ip=13 ;;
        "") user=""; default_ip="" ;;
        *)
            echo "ss: 不支持的用户缩写: ${alias}" >&2
            _usage
            _finish 64
            ;;
    esac

    if [[ -n "${ip_text}" ]]; then
        ip=$((10#${ip_text}))
        if (( ip < 1 || ip > 254 )); then
            echo "ss: IPv4 末位必须在 1-254 之间: ${ip_text}" >&2
            _finish 64
        fi
    else
        ip=${default_ip}
    fi

    if [[ -z "${alias}" ]]; then
        case "${ip}" in
            19) user="kfutfd" ;;
            20) user="kfutfd" ;;
            3) user="zhang" ;;
            2) user="zhangxin" ;;
            4) user="xin" ;;
            11) user="yang" ;;
            12) user="haotian" ;;
            13) user="yanghaotian" ;;
            *) user="${numeric_fallback_user}" ;;
        esac
    fi

    ssh "192.168.188.${ip}" -l "${user}"
    rc=$?
    _finish "${rc}"
}

main "$@"
