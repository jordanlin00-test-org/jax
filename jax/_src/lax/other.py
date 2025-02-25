# Copyright 2020 The JAX Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import math
from typing import Any, Optional, Sequence, Union, cast as type_cast

import jax
from jax._src.numpy import lax_numpy as jnp
from jax._src.lax import lax
from jax._src.lax import convolution

DType = Any

def conv_general_dilated_patches(
    lhs: jax.typing.ArrayLike,
    filter_shape: Sequence[int],
    window_strides: Sequence[int],
    padding: Union[str, Sequence[tuple[int, int]]],
    lhs_dilation: Optional[Sequence[int]] = None,
    rhs_dilation: Optional[Sequence[int]] = None,
    dimension_numbers: Optional[convolution.ConvGeneralDilatedDimensionNumbers] = None,
    precision: Optional[lax.PrecisionType] = None,
    preferred_element_type: Optional[DType] = None,
) -> jax.Array:
  """Extract patches subject to the receptive field of `conv_general_dilated`.

  Runs the input through a convolution with given parameters. The kernel of the
  convolution is constructed such that the output channel dimension `"C"`
  contains flattened image patches, so instead a single `"C"` dimension
  represents, for example, three dimensions `"chw"` collapsed. The order of
  these dimensions is `"c" + ''.join(c for c in rhs_spec if c not in 'OI')`,
  where `rhs_spec == dimension_numbers[1]`, and the size of this `"C"`
  dimension is therefore the size of each patch, i.e.
  `np.prod(filter_shape) * lhs.shape[lhs_spec.index('C')]`, where
  `lhs_spec == dimension_numbers[0]`.

  Docstring below adapted from `jax.lax.conv_general_dilated`.

  See Also:
    https://www.tensorflow.org/xla/operation_semantics#conv_convolution

  Args:
    lhs: a rank `n+2` dimensional input array.
    filter_shape: a sequence of `n` integers, representing the receptive window
      spatial shape in the order as specified in
      `rhs_spec = dimension_numbers[1]`.
    window_strides: a sequence of `n` integers, representing the inter-window
      strides.
    padding: either the string `'SAME'`, the string `'VALID'`, or a sequence of
      `n` `(low, high)` integer pairs that give the padding to apply before and
      after each spatial dimension.
    lhs_dilation: `None`, or a sequence of `n` integers, giving the
      dilation factor to apply in each spatial dimension of `lhs`. LHS dilation
      is also known as transposed convolution.
    rhs_dilation: `None`, or a sequence of `n` integers, giving the
      dilation factor to apply in each spatial dimension of `rhs`. RHS dilation
      is also known as atrous convolution.
    dimension_numbers: either `None`, or a 3-tuple
      `(lhs_spec, rhs_spec, out_spec)`, where each element is a string
      of length `n+2`. `None` defaults to `("NCHWD..., OIHWD..., NCHWD...")`.
    precision: Optional. Either ``None``, which means the default precision for
      the backend, or a :class:`~jax.lax.Precision` enum value (``Precision.DEFAULT``,
      ``Precision.HIGH`` or ``Precision.HIGHEST``).
    preferred_element_type: Optional. Either ``None``, which means the default
      accumulation type for the input types, or a datatype, indicating to
      accumulate results to and return a result with that datatype.

  Returns:
    A rank `n+2` array containing the flattened image patches in the output
    channel (`"C"`) dimension. For example if
    `dimension_numbers = ("NcHW", "OIwh", "CNHW")`, the output has dimension
    numbers `"CNHW" = "{cwh}NHW"`, with the size of dimension `"C"` equal to
    the size of each patch
    (`np.prod(filter_shape) * lhs.shape[lhs_spec.index('C')]`).

  """
  lhs_array = jnp.asarray(lhs)
  filter_shape = tuple(filter_shape)
  dimension_numbers = convolution.conv_dimension_numbers(
      lhs_array.shape, (1, 1) + filter_shape, dimension_numbers)

  lhs_spec, rhs_spec, out_spec = dimension_numbers

  spatial_size = math.prod(filter_shape)
  n_channels = lhs_array.shape[lhs_spec[1]]

  # Move separate `lhs` spatial locations into separate `rhs` channels.
  rhs = jnp.eye(spatial_size, dtype=lhs_array.dtype).reshape(filter_shape * 2)

  rhs = rhs.reshape((spatial_size, 1) + filter_shape)
  rhs = jnp.tile(rhs, (n_channels,) + (1,) * (rhs.ndim - 1))
  rhs = jnp.moveaxis(rhs, (0, 1), (rhs_spec[0], rhs_spec[1]))

  out = convolution.conv_general_dilated(
      lhs=lhs_array,
      rhs=rhs,
      window_strides=window_strides,
      padding=padding,
      lhs_dilation=lhs_dilation,
      rhs_dilation=rhs_dilation,
      dimension_numbers=dimension_numbers,
      precision=None if precision is None else (precision,
                                                lax.Precision.DEFAULT),
      feature_group_count=n_channels,
      preferred_element_type=preferred_element_type
  )
  return out


def conv_general_dilated_local(
    lhs: jax.typing.ArrayLike,
    rhs: jax.typing.ArrayLike,
    window_strides: Sequence[int],
    padding: Union[str, Sequence[tuple[int, int]]],
    filter_shape: Sequence[int],
    lhs_dilation: Optional[Sequence[int]] = None,
    rhs_dilation: Optional[Sequence[int]] = None,
    dimension_numbers: Optional[convolution.ConvGeneralDilatedDimensionNumbers] = None,
    precision: lax.PrecisionLike = None
) -> jax.Array:
  """General n-dimensional unshared convolution operator with optional dilation.

  Also known as locally connected layer, the operation is equivalent to
  convolution with a separate (unshared) `rhs` kernel used at each output
  spatial location. Docstring below adapted from `jax.lax.conv_general_dilated`.

  See Also:
    https://www.tensorflow.org/xla/operation_semantics#conv_convolution

  Args:
    lhs: a rank `n+2` dimensional input array.
    rhs: a rank `n+2` dimensional array of kernel weights. Unlike in regular
      CNNs, its spatial coordinates (`H`, `W`, ...) correspond to output spatial
      locations, while input spatial locations are fused with the input channel
      locations in the single `I` dimension, in the order of
      `"C" + ''.join(c for c in rhs_spec if c not in 'OI')`, where
      `rhs_spec = dimension_numbers[1]`. For example, if `rhs_spec == "WHIO",
      the unfolded kernel shape is
      `"[output W][output H]{I[receptive window W][receptive window H]}O"`.
    window_strides: a sequence of `n` integers, representing the inter-window
      strides.
    padding: either the string `'SAME'`, the string `'VALID'`, or a sequence of
      `n` `(low, high)` integer pairs that give the padding to apply before and
      after each spatial dimension.
    filter_shape: a sequence of `n` integers, representing the receptive window
      spatial shape in the order as specified in
      `rhs_spec = dimension_numbers[1]`.
    lhs_dilation: `None`, or a sequence of `n` integers, giving the
      dilation factor to apply in each spatial dimension of `lhs`. LHS dilation
      is also known as transposed convolution.
    rhs_dilation: `None`, or a sequence of `n` integers, giving the
      dilation factor to apply in each input spatial dimension of `rhs`.
      RHS dilation is also known as atrous convolution.
    dimension_numbers: either `None`, a `ConvDimensionNumbers` object, or
      a 3-tuple `(lhs_spec, rhs_spec, out_spec)`, where each element is a string
      of length `n+2`.
    precision: Optional. Either ``None``, which means the default precision for
      the backend, a ``lax.Precision`` enum value (``Precision.DEFAULT``,
      ``Precision.HIGH`` or ``Precision.HIGHEST``) or a tuple of two
      ``lax.Precision`` enums indicating precision of ``lhs``` and ``rhs``.

  Returns:
    An array containing the unshared convolution result.

  In the string case of `dimension_numbers`, each character identifies by
  position:

  - the batch dimensions in `lhs`, `rhs`, and the output with the character
    'N',
  - the feature dimensions in `lhs` and the output with the character 'C',
  - the input and output feature dimensions in rhs with the characters 'I'
    and 'O' respectively, and
  - spatial dimension correspondences between `lhs`, `rhs`, and the output using
    any distinct characters.

  For example, to indicate dimension numbers consistent with the `conv` function
  with two spatial dimensions, one could use `('NCHW', 'OIHW', 'NCHW')`. As
  another example, to indicate dimension numbers consistent with the TensorFlow
  Conv2D operation, one could use `('NHWC', 'HWIO', 'NHWC')`. When using the
  latter form of convolution dimension specification, window strides are
  associated with spatial dimension character labels according to the order in
  which the labels appear in the `rhs_spec` string, so that `window_strides[0]`
  is matched with the dimension corresponding to the first character
  appearing in rhs_spec that is not `'I'` or `'O'`.

  If `dimension_numbers` is `None`, the default is `('NCHW', 'OIHW', 'NCHW')`
  (for a 2D convolution).
  """
  lhs_array = jnp.asarray(lhs)

  c_precision = lax.canonicalize_precision(precision)
  lhs_precision = type_cast(
      Optional[lax.PrecisionType],
      (c_precision[0]
       if (isinstance(c_precision, tuple) and len(c_precision) == 2)
       else c_precision))

  patches = conv_general_dilated_patches(
      lhs=lhs_array,
      filter_shape=filter_shape,
      window_strides=window_strides,
      padding=padding,
      lhs_dilation=lhs_dilation,
      rhs_dilation=rhs_dilation,
      dimension_numbers=dimension_numbers,
      precision=lhs_precision
  )

  lhs_spec, rhs_spec, out_spec = convolution.conv_dimension_numbers(
      lhs_array.shape, (1, 1) + tuple(filter_shape), dimension_numbers)

  lhs_c_dims, rhs_c_dims = [out_spec[1]], [rhs_spec[1]]

  lhs_b_dims = out_spec[2:]
  rhs_b_dims = rhs_spec[2:]

  rhs_b_dims = [rhs_b_dims[i] for i in sorted(range(len(rhs_b_dims)),
                                              key=lambda k: lhs_b_dims[k])]
  lhs_b_dims = sorted(lhs_b_dims)

  dn = ((lhs_c_dims, rhs_c_dims), (lhs_b_dims, rhs_b_dims))
  out = lax.dot_general(patches, rhs, dimension_numbers=dn, precision=precision)
  out = jnp.moveaxis(out, (-2, -1), (out_spec[0], out_spec[1]))
  return out
