#!/usr/bin/env python3
"""
Cache Manager CLI for Gemini Context Caching

Usage:
    python cache_manager.py list                    # List all caches
    python cache_manager.py create <prompt_file>    # Create cache from file
    python cache_manager.py delete <cache_name>     # Delete specific cache
    python cache_manager.py cleanup                 # Delete all caches
    python cache_manager.py info <cache_name>       # Get cache details
"""

import argparse
import os
import sys
from datetime import datetime

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: google-genai package not installed")
    print("Run: pip install google-genai")
    sys.exit(1)


def get_client():
    """Initialize Gemini client."""
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    return genai.Client()


def list_caches(args):
    """List all caches."""
    client = get_client()
    caches = list(client.caches.list())
    
    if not caches:
        print("No caches found.")
        return
    
    print(f"\n{'Name':<60} {'Tokens':<10} {'Expires':<25}")
    print("-" * 95)
    
    for cache in caches:
        name = cache.name.split("/")[-1][:55]
        tokens = cache.usage_metadata.total_token_count if cache.usage_metadata else "N/A"
        expires = cache.expire_time.isoformat() if cache.expire_time else "N/A"
        print(f"{name:<60} {tokens:<10} {expires:<25}")
    
    print(f"\nTotal caches: {len(caches)}")


def create_cache(args):
    """Create a new cache from a prompt file."""
    client = get_client()
    
    # Read prompt file
    if not os.path.exists(args.prompt_file):
        print(f"Error: File not found: {args.prompt_file}")
        sys.exit(1)
    
    with open(args.prompt_file, "r", encoding="utf-8") as f:
        system_prompt = f.read()
    
    # Count tokens first
    token_count = client.models.count_tokens(
        model=args.model,
        contents=system_prompt
    )
    
    print(f"Prompt tokens: {token_count.total_tokens}")
    
    min_tokens = 2048 if "flash" in args.model else 4096
    if token_count.total_tokens < min_tokens:
        print(f"Warning: Token count below minimum ({min_tokens}) for caching")
        if not args.force:
            print("Use --force to create anyway (will use implicit caching)")
            sys.exit(1)
    
    # Create cache
    cache = client.caches.create(
        model=args.model,
        config=types.CreateCachedContentConfig(
            display_name=args.name or f"cache-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            system_instruction=system_prompt,
            ttl=f"{args.ttl}s",
        )
    )
    
    print(f"\n✅ Cache created successfully!")
    print(f"   Name: {cache.name}")
    print(f"   Display name: {cache.display_name}")
    print(f"   Tokens: {cache.usage_metadata.total_token_count}")
    print(f"   Expires: {cache.expire_time}")
    print(f"\nUse this in your code:")
    print(f'   cached_content="{cache.name}"')


def delete_cache(args):
    """Delete a specific cache."""
    client = get_client()
    
    try:
        client.caches.delete(args.cache_name)
        print(f"✅ Deleted cache: {args.cache_name}")
    except Exception as e:
        print(f"Error deleting cache: {e}")
        sys.exit(1)


def cleanup_caches(args):
    """Delete all caches."""
    client = get_client()
    caches = list(client.caches.list())
    
    if not caches:
        print("No caches to delete.")
        return
    
    if not args.force:
        print(f"About to delete {len(caches)} cache(s):")
        for cache in caches:
            print(f"  - {cache.display_name or cache.name}")
        
        confirm = input("\nContinue? [y/N]: ")
        if confirm.lower() != "y":
            print("Aborted.")
            return
    
    for cache in caches:
        try:
            client.caches.delete(cache.name)
            print(f"✅ Deleted: {cache.display_name or cache.name}")
        except Exception as e:
            print(f"❌ Failed to delete {cache.name}: {e}")
    
    print(f"\nCleanup complete.")


def cache_info(args):
    """Get detailed info about a cache."""
    client = get_client()
    
    try:
        cache = client.caches.get(name=args.cache_name)
        
        print(f"\n{'='*60}")
        print(f"Cache Details")
        print(f"{'='*60}")
        print(f"Name:         {cache.name}")
        print(f"Display name: {cache.display_name}")
        print(f"Model:        {cache.model}")
        print(f"Create time:  {cache.create_time}")
        print(f"Update time:  {cache.update_time}")
        print(f"Expire time:  {cache.expire_time}")
        
        if cache.usage_metadata:
            print(f"\nUsage:")
            print(f"  Total tokens: {cache.usage_metadata.total_token_count}")
        
        # Calculate TTL remaining
        if cache.expire_time:
            remaining = cache.expire_time - datetime.now(cache.expire_time.tzinfo)
            print(f"\nTime remaining: {remaining}")
        
    except Exception as e:
        print(f"Error getting cache info: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Manage Gemini context caches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # List command
    subparsers.add_parser("list", help="List all caches")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new cache")
    create_parser.add_argument("prompt_file", help="Path to system prompt file")
    create_parser.add_argument("--name", help="Display name for the cache")
    create_parser.add_argument("--model", default="gemini-2.5-flash-001", 
                              help="Model to use (default: gemini-2.5-flash-001)")
    create_parser.add_argument("--ttl", type=int, default=3600,
                              help="TTL in seconds (default: 3600)")
    create_parser.add_argument("--force", action="store_true",
                              help="Force creation even if below token minimum")
    
    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a cache")
    delete_parser.add_argument("cache_name", help="Cache name to delete")
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Delete all caches")
    cleanup_parser.add_argument("--force", "-f", action="store_true",
                               help="Skip confirmation")
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Get cache details")
    info_parser.add_argument("cache_name", help="Cache name")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    commands = {
        "list": list_caches,
        "create": create_cache,
        "delete": delete_cache,
        "cleanup": cleanup_caches,
        "info": cache_info,
    }
    
    commands[args.command](args)


if __name__ == "__main__":
    main()
