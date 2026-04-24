"""Startup logging — shows component config and env var status."""
import os

def _check(var: str) -> str:
    return "✅" if os.getenv(var) else "❌"

def _val(var: str, hide: bool = False) -> str:
    v = os.getenv(var, "")
    if not v:
        return "not set"
    return "***" if hide else v

def banner(component: str, extras: dict = None):
    print(f"\n{'═' * 50}")
    print(f"  {component}")
    print(f"{'═' * 50}")
    if extras:
        for k, v in extras.items():
            print(f"  {k:<22s} {v}")
    print(f"{'─' * 50}")

def env_status():
    """Print all env var status."""
    print(f"\n  Environment:")
    print(f"    MongoDB:")
    print(f"      {_check('MONGODB_URI')} MONGODB_URI          {_val('MONGODB_URI')}")
    print(f"      {_check('MONGODB_USER')} MONGODB_USER         {_val('MONGODB_USER')}")
    print(f"      {_check('MONGODB_PASS')} MONGODB_PASS         {_val('MONGODB_PASS', hide=True)}")
    print(f"    News sources:")
    print(f"      {_check('NEWSAPI_KEY')} NEWSAPI_KEY          {'set' if os.getenv('NEWSAPI_KEY') else 'not set (source disabled)'}")
    print(f"      {_check('FINNHUB_KEY')} FINNHUB_KEY          {'set' if os.getenv('FINNHUB_KEY') else 'not set (source disabled)'}")
    print(f"      {_check('TWITTER_BEARER_TOKEN')} TWITTER_BEARER_TOKEN {'set' if os.getenv('TWITTER_BEARER_TOKEN') else 'not set (source disabled)'}")
    print(f"      ✅ RSS                  always on")
    print(f"      ✅ Reddit               always on")
    print(f"    Analyzer:")
    print(f"      {_check('OPENAI_API_KEY')} OPENAI_API_KEY       {'LLM mode' if os.getenv('OPENAI_API_KEY') else 'keyword mode (free)'}")
    print(f"    Broker:")
    print(f"      BROKER={os.getenv('BROKER', 'log')}")
    if os.getenv("BROKER", "").lower() == "alpaca":
        print(f"      {_check('ALPACA_API_KEY')} ALPACA_API_KEY")
        print(f"      {_check('ALPACA_SECRET_KEY')} ALPACA_SECRET_KEY")
    if os.getenv("BROKER", "").lower() == "futu":
        print(f"      FUTU_REAL={'yes' if os.getenv('FUTU_REAL') else 'no (simulate)'}")
    print(f"    Redis (distributed only):")
    print(f"      REDIS_HOST={os.getenv('REDIS_HOST', 'localhost')}")
