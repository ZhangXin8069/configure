#!/usr/bin/env bash
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
cat > .ddub.sh <<'EOF'
#!/bin/bash
#DSUB --mpi hmpi
#DSUB -q q_hpcapp
#DSUB -n qcu
#DSUB -x job
#DSUB -nn 1
#DSUB -rpn 16
#DSUB -N 16
#DSUB -R "cpu=37;mem=8G"
#DSUB -oo output.txt
#DSUB -eo error.txt
#DSUB -T 600
source "${HOME}/env.sh"
EOF
printf '%s ' "$@" >> .ddub.sh
printf '>log.txt 2>&1\n' >> .ddub.sh
dsub -s ./.ddub.sh
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
