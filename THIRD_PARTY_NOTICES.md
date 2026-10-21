# Third-Party Notices

The following MIT-licensed projects informed small, rewritten adaptations in this repository. Their
upstream sources remain pinned as read-only submodules under `refer/git-rep/`; this repository does not
vendor their complete source trees.

## Matt Pocock skills

- Source: https://github.com/mattpocock/skills.git
- Fixed commit: `5beb35b040e3de97e54fa9e386d7e42d15c295c2`
- Copyright (c) 2026 Matt Pocock
- Local adaptations: `skills/skill-creator/references/agent-doc-writing.md`,
  `skills/plan/references/tracer-tickets.md`, and `skills/review/references/review-matrix.md`.

## oh-my-codex

- Source: https://github.com/Yeachan-Heo/oh-my-codex.git
- Fixed commit: `304fb3b4825c4132c273732b14d2d5e86b54f8e3`
- Copyright (c) 2026 Yeachan-Heo
- Local adaptations: `skills/review/references/review-matrix.md`,
  `skills/brainstorm/SKILL.md`, `skills/research-notes/SKILL.md`,
  `skills/test/references/adversarial-qa.md`, `hooks/agent-hook.sh`, and
  `tools/plugin-audit.py`.

## Scientific Agent Skills

- Source: https://github.com/K-Dense-AI/scientific-agent-skills.git
- Fixed commit: `593377bb048752abb0152deab9fbb1083a6087df`
- Copyright (c) 2025 K-Dense Inc.
- Local adaptations: `skills/phys-model/references/uncertainty-and-evidence.md` and
  `tools/agent-resources.py`.

## MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Academic Research Skills

`academic-research-skills` is retained only as a read-only reference at fixed commit
`cfd081d8f309ec65254d9f9f04c845ee78b1ec1d` under `CC BY-NC 4.0`. No source code or skill text from that
project is copied into this repository's runtime paths.

## Awesome LLM Apps

`llm-skills` is retained only as a read-only reference at fixed commit
`874bc13a57aa2ba1266a84f2444808ce3093efb6` under Apache-2.0. No skill text or source code from that
submodule is copied into this repository's runtime paths by the 2026-10-21 absorption.

## Andrej Karpathy Skills

`andrej-karpathy-skills` is retained only as a read-only reference at fixed commit
`2c606141936f1eeef17fa3043a72095b4765b9c2` under MIT. No skill text is copied into this
repository's runtime paths by the 2026-10-21 absorption.

## NVIDIA Skills

`cuda-skills` is retained only as a read-only reference at fixed commit
`c31020eec34541c0f08d3e4a84eedefe1c002872` under Apache-2.0 / CC-BY-4.0 as indicated by the
upstream per-content notices. No skill text or source code is copied into this repository's runtime paths.

## ECC Skills

`ecc-skills` is retained only as a read-only reference at fixed commit
`90606c8315ee09cafc303515c5f33024db6b9882` under MIT, Copyright (c) 2026 Affaan Mustafa.
Its hook/plugin schema and audit patterns informed `hooks/agent-hook.sh` and `tools/plugin-audit.py`;
no skill text or complete implementation is copied into this repository's runtime paths.
