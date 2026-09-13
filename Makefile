# Makefile for GroupOffice MCP Server

.PHONY: help install install-dev test lint format type-check clean build run dev

help:
	@echo "Available commands:"
	@echo "  install      Install the package"
	@echo "  install-dev  Install package with development dependencies"
	@echo "  test         Run tests"
	@echo "  lint         Run linting (ruff)"
	@echo "  clean        Clean build artifacts"
	@echo "  build        Build the package"
	@echo "  run          Run the MCP server"
	@echo "  dev          Run the MCP server with debug logging"

install:
	pip install .

install-dev:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=groupoffice_mcp_server --cov-report=html --cov-report=term

lint:
	ruff check src/ tests/

clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +

build: clean
	python -m build

run:
	python -m groupoffice_mcp_server.server

dev:
	GROUPOFFICE_DEBUG=true python -m groupoffice_mcp_server.server

dev-env:
	@echo "Copy .env.example to .env and customize as needed:"
	@echo "cp .env.example .env"
