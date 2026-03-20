_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
sudo swapoff -a
sudo dd if=/dev/zero of=/var/swapfile bs=1M count=65536
sudo mkswap /var/swapfile
sudo swapon /var/swapfile
# sudo echo "/var/swapfile swap swap defaults 0 0" >> /etc/fstab
# sudo sysctl vm.swappiness=0
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
