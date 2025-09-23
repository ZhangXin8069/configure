#!/bin/bash
#SBATCH -J IMP_ZHANGXIN #作业名称
#SBATCH -p newlarge #队列名称
#SBATCH -N 8 #需要几个节点
#SBATCH --ntasks-per-node=8 #单节点多少个rank
#SBATCH --cpus-per-task=16 #每个rank 需要多少个cpu核
#SBATCH --gres=dcu:8 #单节点多少张dcu卡
#SBATCH -o %j #输出日志
#SBATCH -e %j #错误日志
module purge #清空module
source env.sh
pushd ~/PyQCU/test
# bash test.clover.bistabcg-npX-test6.sh
# bash test.clover.bistabcg-npX-test7.sh
bash test.clover.bistabcg-npX-test8.sh
bash test.clover.bistabcg-npX-test9.sh
popd
