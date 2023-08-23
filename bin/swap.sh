sudo swapoff -a
sudo dd if=/dev/zero of=/var/swapfile bs=1M count=16384
sudo mkswap /var/swapfile
sudo swapon /var/swapfile
# sudo echo "/var/swapfile swap swap defaults 0 0" >> /etc/fstab
# sudo sysctl vm.swappiness=10
