#!/usr/bin/env bash
_SRC=${BASH_SOURCE[0]:-${0}}
case "${_SRC}" in */*) _DIR=${_SRC%/*}; [ -z "${_DIR}" ] && _DIR="/";; *) _DIR=.;; esac
if [[ "${_DIR}" == /* ]]; then _PATH="${_DIR}"; else _PATH=$(cd "${_DIR}" && pwd); fi
_NAME=${_SRC##*/}
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
sudo swapoff -a
sudo dd if=/dev/zero of=/var/swapfile bs=1M count=65536
sudo mkswap /var/swapfile
sudo swapon /var/swapfile
# sudo echo "/var/swapfile swap swap defaults 0 0" >> /etc/fstab
# sudo sysctl vm.swappiness=0
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
