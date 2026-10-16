#!/usr/bin/env python3
from concat_automation.cli import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (Exception, SystemExit) as error:
        if isinstance(error, SystemExit):
            raise
        raise SystemExit(str(error)) from error
