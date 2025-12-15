# Old-style dependency tests

The test files in this folder use the old (pre-v0.0.12) dependency mechanism. This will be removed in v0.1.0, and these tests are preserved here to ensure they work until then. Test files of the same name exist in the parent module, but they have been migrated to use the newer syntax (i.e. not to use dependencies). As of v0.1.0, this folder will be deleted, and the duplication will go away.

It felt cleaner to duplicate the tests temporarily, rather than try to test two different forms of the syntax in the same file. This way, we keep the old syntax out of the test suite, preserving enough to check it's not broken until it moves from deprecated to gone.
