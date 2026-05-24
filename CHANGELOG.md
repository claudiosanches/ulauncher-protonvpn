# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-05-24

### Added

- **ProtonVPN CLI integration**: All VPN operations delegated to the `protonvpn`
  Linux CLI wrapper.
- **Country browsing**: Search and filter all available ProtonVPN countries with
  flag icons using ISO 3166-1 alpha-2 codes.
- **City drill-down**: Select a country to see available cities and their
  supported features (P2P, Tor, etc.), then connect to a specific city.
- **Fastest server**: Connect to the globally fastest server or the fastest in a
  chosen country with a single keystroke.
- **Live connection status**: Displays connected server name, load, protocol, and
  current IP in the results list.
- **Background Actions**: Fluid UI experience with connections handled in background threads.
- **Disconnect action**: Disconnect from any state directly from the launcher.
