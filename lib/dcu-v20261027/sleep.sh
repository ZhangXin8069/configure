#!/bin/bash

#SBATCH --partition=kshdnormal
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=8
#SBATCH --job-name=sleep
#SBATCH --gres=dcu:4
#SBATCH --exclusive
#SBATCH --output=%j.log
#SBATCH --error=%j.err

source /public/home/sunpeng_1/env.sh
sleep 600s
