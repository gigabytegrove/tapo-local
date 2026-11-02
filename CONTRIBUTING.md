# Contributing to Tapo Local

Thanks for helping. Bug reports and device suggestions are welcome even if you do not write code.

## Branch policy

- **dev:** All ongoing development, documentation updates, and tests. Open working pull requests against dev.
- **main:** The public release branch. Only tested changes are promoted from dev to main through a release pull request.
- The only long-lived branches are dev and main. Do not push development fixes directly to main.

## Before submitting a change

1. Check [existing issues](https://github.com/gigabytegrove/tapo-local/issues).
2. Read [README.md](README.md), [SUPPORTED_DEVICES.md](SUPPORTED_DEVICES.md), and the [changelog](CHANGELOG.md).
3. Keep your change focused. Preserve the Home Assistant domain (tapo_local), existing config entries, device IDs, saved sessions and entity identities.
4. Add tests for behavior changes and explain any live hardware tests you did or could not do.
5. Update the changelog for visible changes. Write it in ordinary language: what changed, who is affected, what to do after upgrading, and any limitations.
6. Do not commit passwords, tokens, encryption keys, pairing codes, private sessions, or full unredacted diagnostic exports.

## Run tests for developers

Use Python 3.13 or the version specified in the [validation workflow](.github/workflows/validate.yml), from the repository root:

~~~bash
python3 -m pip install 'python-kasa[speedups]==0.11.0.1'
python3 -m compileall -q custom_components/tapo_local
python3 -m unittest discover -s tests -v
python3 tools/render_release_notes.py 0.7.9
~~~

These commands are for a separate development environment, not for installing Tapo Local inside Home Assistant. Normal Home Assistant installations manage their Python dependencies automatically.

## Release notes and reviews

- The installed version is read from custom_components/tapo_local/manifest.json.
- Add a matching version heading to CHANGELOG.md before requesting a public version bump.
- Use **Added**, **Changed**, **Fixed**, **Security**, **Upgrade notes**, and **Known limitations** when relevant. Do not invent tests or claim real-device verification based on CI.
- A public version is released only after a reviewed dev-to-main pull request and passing validation. Documentation-only dev commits do not change the public version.
- Follow the [pull request template](.github/PULL_REQUEST_TEMPLATE.md), [security policy](SECURITY.md), and [code of conduct](CODE_OF_CONDUCT.md).
