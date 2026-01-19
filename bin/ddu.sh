#!/bin/bash
dir_path="${1:-.}"
depth="${2:-2}"
command="du -h -d ${depth} ${dir_path} | sort -h"
echo "command: ${command}"
eval "${command}"