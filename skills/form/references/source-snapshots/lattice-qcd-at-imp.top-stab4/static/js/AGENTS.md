# AGENTS.md — static/js/

站点 JS 模块（IIFE + window 全局命名空间：`I18N`/`Theme`/`MusicPlayer`/`Papers`/`Animations`），
`langChanged` 自定义事件通信。index.html 中 defer 加载顺序（勿乱改）：

```
fontawesome-subset.js → bulma-carousel.min.js → bulma-slider.min.js
→ i18n.js → theme.js → music.js → papers.js → animations.js → index.js
```

- `fontawesome-subset.js` — 图标精简版（由 tools/fa_subset.py 生成，勿手改）
- `fontawesome.all.min.js` — FontAwesome 全量图标源
- `i18n.js` — 语言切换（data/translations.json）
- `theme.js` — 深色/浅色主题切换（跟随系统偏好）
- `music.js` — 背景音乐播放器
- `papers.js` — 论文列表（data/papers.json，含离线回退 custom/inspirehep.net/）
- `animations.js` — Canvas 背景动画（深色=星场、浅色=樱花雨）
- `index.js` — 页面主逻辑（板块渲染、事件绑定）
