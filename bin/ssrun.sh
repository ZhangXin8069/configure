#!/bin/bash
command=$@
echo "command:${command}"
clear
source $HOME/env.sh
echo "srun -J ssrun -p gpu-debug -n 2 --time=00-00:30:00 --output=ssrun.out --error=ssrun.err --mail-user=zhangxin8069@qq.com --mail-type=ALL --gres=gpu:2 ${command}"
srun -J ssrun -p gpu-debug -n 2 --time=00-00:30:00 --output=ssrun.out --error=ssrun.err --mail-user=zhangxin8069@qq.com --mail-type=ALL --gres=gpu:2 ${command}
