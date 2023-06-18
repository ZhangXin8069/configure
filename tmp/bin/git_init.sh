git config --global user.name "zhangxin"
git config --global user.email "zhangxin8069@qq.com"
ssh-keygen -t ed25519 -C "zhangxin8069@qq.com"
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
echo -e "id_rsa.pub:\n"
cat ~/.ssh/id_ed25519.pub
echo -e "\nput this to github's ssh.then run\"ssh -T git@github.com\""

