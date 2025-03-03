# Database Management

## Automatic Database Reset
To reset the database and recreate all tables, run:
```bash
python reset_database.py
```

This script will:
1. Drop all existing tables
2. Recreate the database schema
3. Add sample data (if available)

## Manual Database Reset
If you need to manually reset the database using SQL, you can use these commands:

```sql
-- Connect to your database first, then:

-- Drop all tables (this will be executed by the reset script)
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;

-- After dropping, you can recreate tables using:
python main.py
```

Note: The automatic reset script (reset_database.py) is the recommended method as it ensures proper schema recreation and can populate sample data.
