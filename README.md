# Knowledge Catalog

[Knowledge Catalog](https://cloud.google.com/products/knowledge-catalog) (formerly Dataplex), is an AI-powered data catalog and metadata management platform. It provides a dynamic knowledge graph of all your data, structured and unstructured, to provide semantics and business context to AI agents

This repository features tools, agents, and samples that demonstrate Knowledge Catalog features, and building context management, enrichment and retrieval solutions.

## Agent Plugin

The repository root is an [Agent Plugins v1.0.0](https://agent-plugins.org/) package:

- `plugin.json` is the portable manifest.
- `skills/` contains portable Agent Skills for catalog discovery and local workflow memory.
- `mcp.json` starts a read-only Knowledge Catalog search surface and a DuckDB-backed local memory/work-item store.

The MCP process stores state in the client-provided `PLUGIN_DATA` directory, so plugin updates do not erase it. DuckDB is the persistence/query layer; the agent still decides and executes work. This does not replace a client's built-in memory automatically—the compatible client must load the plugin and invoke its tools.

The server requires `uv` and Python 3.11 or newer. Its first launch may need network access to resolve locked Python dependencies. Knowledge Catalog search additionally requires Google Cloud Application Default Credentials and `dataplex.projects.search` permission.

DuckDB community extensions are disabled by default. The closed extension policy supports opt-in `agent_data` for read-only Codex history lookup; enabling it downloads and executes signed third-party code with the MCP process's user privileges. See [`agent-plugin/README.md`](agent-plugin/README.md) for development and security details.


## Getting Started

[![Open in Cloud Shell](http://gstatic.com/cloudssh/images/open-btn.svg)](https://console.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https%3A%2F%2Fgithub.com%2FGoogleCloudPlatform%2Fknowledge-catalog.git)


## Contributing

See the contributing [instructions](CONTRIBUTING.md) to get started contributed.


## License

All solutions within this repository are provided under the [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0) license. Please see [LICENSE](LICENSE.md) for more detailed terms and conditions.


## Disclaimer

This repository and its contents are not an official Google product.
