.. note::
   **Windows Installations on devices with ARM Processors**

   Installing on Windows devices with ARM processors requires `Visual Studio`_ with the **"Desktop development with C++"** workload enabled. This is necessary because ``pydantic`` relies on Rust_, which in turn requires C++ build tools to compile.

   *If you are using a centrally managed machine, you will need administrator privileges to install these system-level dependencies.*