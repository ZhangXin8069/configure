_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
command=$@
source $HOME/env.sh
srun -J ssrun -p gpu-debug -n 2 --time=00-00:30:00 --output=ssrun.out --error=ssrun.err --mail-user=zhangxin8069@qq.com --mail-type=ALL --gres=gpu:2 ${command}
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
