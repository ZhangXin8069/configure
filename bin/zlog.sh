#!/bin/bash
command=$@
echo "command:${command}"
echo "${command} > .log.txt 2>&1 &"
${command} >.log.txt 2>&1 &
watch -n 0.1 tail .log.txt
