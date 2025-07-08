# from fluidkit import integrate
# from tests.sample.app import app

# integrate(app)

from fluidkit.core.integrator import test_integration
from fluidkit.core.config import test_config_management
from fluidkit.generators.typescript.imports import test_config_driven_imports, test_imports
from fluidkit.generators.typescript.pipeline import test_config_driven_generation

test_imports()
# test_integration()
# test_config_management()
# test_config_driven_imports()
# test_config_driven_generation()

from tests.sample.app import app
import fluidkit

fluidkit.integrate(app)
