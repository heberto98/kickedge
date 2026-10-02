import sys

# Route offline inference before importing the historical ingestion/config layer.
if len(sys.argv)>1 and sys.argv[1]=='infer':
    from .inference.cli import main
    main(sys.argv[2:])
else:
    from .cli import main
    main()
