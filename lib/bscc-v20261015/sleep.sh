#!/bin/bash
#SBATCH -J QCU-TEST
#SBATCH --output=%j.out
#SBATCH --error=%j.err
#SBATCH --gpus=1
#SBATCH --time=5

source /home/bingxing2/home/scx8080/configure/lib/bscc-v20261015/env.sh
sleep 600s
