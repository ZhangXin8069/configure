_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
ssh weiwang@bl-0.inpac.sjtu.edu.cn
# scp weiwang@bl-0.inpac.sjtu.edu.cn:/home/weiwang/profiler/trace_20260407140930_0.json .
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
