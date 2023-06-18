sudo cpupower -c all frequency-set -g performance
sudo cpupower idle-set -e 0
sudo cpupower idle-set -d 1
sudo cpupower idle-set -d 2
sudo cpupower idle-set -d 3
watch -n 0.1 sudo cpupower monitor
