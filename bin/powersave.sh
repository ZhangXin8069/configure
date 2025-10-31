sudo cpupower -c all frequency-set -g powersave
sudo cpupower idle-set -d 0
sudo cpupower idle-set -d 1
sudo cpupower idle-set -d 2
sudo cpupower idle-set -e 3
watch -n 0.1 sudo cpupower monitor
