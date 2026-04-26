if [ -f /testbed/conftest.py ]; then
    echo 'Backing up existing /testbed/conftest.py'
    cp /testbed/conftest.py /testbed/conftest.py.bak
fi
echo 'Installing trace collector conftest.py'
cp /opt/tracers/pytest_tracer.py /testbed/conftest.py
chmod 644 /testbed/conftest.py
if [ ! -f /testbed/conftest.py ]; then
    echo 'ERROR: Failed to install conftest.py'
    exit 1
fi
echo 'Trace collection setup complete (pytest)'
