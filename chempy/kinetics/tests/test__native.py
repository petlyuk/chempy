# -*- coding: utf-8 -*-
from __future__ import (absolute_import, division, print_function)

from collections import defaultdict

try:
    import numpy as np
except ImportError:
    np = None

import pytest

from chempy import ReactionSystem
from chempy.util.testing import requires
from ..ode import get_odesys
from .._native import get_native


decay_analytic = {
    0: lambda y0, k, t: (
        y0[0] * np.exp(-k[0]*t)),
    1: lambda y0, k, t: (
        y0[1] * np.exp(-k[1] * t) + y0[0] * k[0] / (k[1] - k[0]) *
        (np.exp(-k[0]*t) - np.exp(-k[1]*t))),
    2: lambda y0, k, t: (
        y0[2] * np.exp(-k[2] * t) + y0[1] * k[1] / (k[2] - k[1]) *
        (np.exp(-k[1]*t) - np.exp(-k[2]*t)) +
        k[1] * k[0] * y0[0] / (k[1] - k[0]) *
        (1 / (k[2] - k[0]) * (np.exp(-k[0]*t) - np.exp(-k[2]*t)) -
         1 / (k[2] - k[1]) * (np.exp(-k[1]*t) - np.exp(-k[2]*t))))
}


def decay_get_Cref(k, y0, tout):
    coeffs = list(k) + [0]*(3-len(k))

    return np.column_stack([
        decay_analytic[i](y0, coeffs, tout) for i in range(
            min(3, len(k)+1))])


@requires('pycvodes', 'pyodesys')
@pytest.mark.parametrize('solve', [(), ('CNO',)])
def test_get_native__first_step(solve):
    integrator = 'cvode'
    forgive = 20

    def k(num):
        return "MassAction(unique_keys=('k%d',))" % num

    lines = [  # fictitious isomerization
        "CNO -> ONC; %s" % k(1),
        "ONC -> NCO; %s" % k(2),
        "NCO -> CON; %s" % k(3)
    ]
    rsys = ReactionSystem.from_string('\n'.join(lines), 'CNO ONC NCO CON')
    odesys, extra = get_odesys(rsys, include_params=False)
    if len(solve) > 0:
        from pyodesys.symbolic import PartiallySolvedSystem
        odesys = PartiallySolvedSystem(odesys, extra['linear_dependencies'](solve))
    c0 = defaultdict(float, {'CNO': .7})
    rate_coeffs = (1e78, 2, 3.)
    args = (5, c0, dict(zip('k1 k2 k3'.split(), rate_coeffs)))
    kwargs = dict(integrator=integrator, atol=1e-9, rtol=1e-9, nsteps=1000)
    native = get_native(rsys, odesys, integrator)

    h0 = extra['max_euler_step_cb'](0, *args[1:])
    xout1, yout1, info1 = odesys.integrate(*args, first_step=h0, **kwargs)
    xout2, yout2, info2 = native.integrate(*args, **kwargs)
    ref1 = decay_get_Cref(rate_coeffs, [c0[key] for key in native.names], xout1)
    ref2 = decay_get_Cref(rate_coeffs, [c0[key] for key in native.names], xout2)
    allclose_kw = dict(atol=kwargs['atol']*forgive, rtol=kwargs['rtol']*forgive)

    assert np.allclose(yout1[:, :3], ref1, **allclose_kw)

    assert info2['success']
    assert info2['nfev'] > 10 and info2['nfev'] > 1 and info2['time_cpu'] < 10 and info2['time_wall'] < 10
    assert np.allclose(yout2[:, :3], ref2, **allclose_kw)
