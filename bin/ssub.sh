_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
command=$@
echo "#!/bin/bash 
#SBATCH --job-name=ssub
#SBATCH --partition=gpu-debug
#SBATCH --nodes=1
# #SBATCH --cpus-per-task=1
#SBATCH -n 2
# # SBATCH --ntasks-per-node=48
# #SBATCH --nodelist=node[3,4]
# #SBATCH --exclude=node[1,5-6]
#SBATCH --time=00-00:30:00
#SBATCH --output=ssub.out
#SBATCH --error=ssub.err
#SBATCH --mail-type=ALL
#SBATCH --mail-user=zhangxin8069@qq.com
#SBATCH --gres=gpu:2
source ${HOME}/env.sh
" >.ssub.sh
echo ${command} >>.ssub.sh
sbatch ./.ssub.sh
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
