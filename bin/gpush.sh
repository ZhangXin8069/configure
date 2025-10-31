# source
_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
# pushd ${_PATH}/../
# source ./env.sh
# popd

# init
_NAME=$(basename "$0")

# do
echo "###${_NAME} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
echo "git add * && git commit -m $(date "+%Y-%m-%d-%H-%M-%S") && git push"
git add .gitignore
git push origin --tags
git add * && git commit -m $(date "+%Y-%m-%d-%H-%M-%S") && git push
echo "###${_NAME} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"

# done
