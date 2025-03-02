# -*- coding: utf-8 -*-
# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for `tf.data.Dataset.padded_batch()`."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from absl.testing import parameterized
import numpy as np

from tensorflow.python.data.kernel_tests import checkpoint_test_base
from tensorflow.python.data.kernel_tests import test_base
from tensorflow.python.data.ops import dataset_ops
from tensorflow.python.framework import combinations
from tensorflow.python.framework import constant_op
from tensorflow.python.framework import dtypes
from tensorflow.python.framework import errors
from tensorflow.python.framework import sparse_tensor
from tensorflow.python.framework import tensor_shape
from tensorflow.python.ops import array_ops
from tensorflow.python.ops import math_ops
from tensorflow.python.ops import string_ops
from tensorflow.python.ops.ragged import ragged_tensor_value
from tensorflow.python.platform import test
from tensorflow.python.util import compat


class PaddedBatchTest(test_base.DatasetTestBase, parameterized.TestCase):

  @combinations.generate(
      combinations.times(
          test_base.default_test_combinations(),
          combinations.combine(
              count=[32, 34],
              padded_shapes=[[None], [25]],
              drop_remainder=[True, False])))
  def testPaddedBatchDataset(self, count, padded_shapes, drop_remainder):
    seq_lens = np.random.randint(20, size=(count,)).astype(np.int32)
    batch_size = 4
    dataset = dataset_ops.Dataset.from_tensor_slices(seq_lens).map(
        lambda x: array_ops.fill([x], x)).padded_batch(
            batch_size=batch_size,
            drop_remainder=drop_remainder,
            padded_shapes=padded_shapes)

    num_full_batches = len(seq_lens) // batch_size
    get_next = self.getNext(dataset)
    for i in range(num_full_batches):
      result = self.evaluate(get_next())
      padded_len = padded_shapes[0]
      if padded_len is None or padded_len == -1:
        padded_len = np.max(result) if result.size > 0 else 0
      self.assertEqual((batch_size, padded_len), result.shape)
      for j in range(batch_size):
        seq_len = seq_lens[(i * batch_size) + j]
        self.assertAllEqual(result[j, :seq_len], [seq_len] * seq_len)
        self.assertAllEqual(result[j, seq_len:], [0] * (padded_len - seq_len))

    if not drop_remainder and len(seq_lens) % batch_size > 0:
      result = self.evaluate(get_next())
      padded_len = padded_shapes[0]
      if padded_len is None or padded_len == -1:
        padded_len = np.max(result) if result.size > 0 else 0
      self.assertEqual((len(seq_lens) % batch_size, padded_len), result.shape)
      for j in range(len(seq_lens) % batch_size):
        seq_len = seq_lens[num_full_batches * batch_size + j]
        self.assertAllEqual(result[j, :seq_len], [seq_len] * seq_len)
        self.assertAllEqual(result[j, seq_len:], [0] * (padded_len - seq_len))

    with self.assertRaises(errors.OutOfRangeError):
      self.evaluate(get_next())
    with self.assertRaises(errors.OutOfRangeError):
      self.evaluate(get_next())

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchShortPadding(self):
    dataset = (
        dataset_ops.Dataset.from_tensor_slices(
            [6, 5, 5, 5, 5]).map(lambda x: array_ops.fill([x], x)).padded_batch(
                batch_size=4, padded_shapes=[5]))
    self.assertDatasetProduces(
        dataset, expected_error=(errors.DataLossError, ''))

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchEmptyTensors(self):
    dataset = (
        dataset_ops.Dataset.from_tensor_slices(
            [0, 0, 0, 0]).map(lambda x: array_ops.fill([x], x)).padded_batch(
                batch_size=4, padded_shapes=[-1]))
    self.assertDatasetProduces(dataset, expected_output=[[[], [], [], []]])

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchWithDifferetElementTypes(self):
    dataset = dataset_ops.Dataset.from_tensor_slices(
        ([0, 1, 2, 3], ['a', 'b', 'c', 'd']))
    dataset = dataset.padded_batch(2)
    self.assertDatasetProduces(dataset, [([0, 1], ['a', 'b']),
                                         ([2, 3], ['c', 'd'])])

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchWithEmptyTuple(self):
    dataset = dataset_ops.Dataset.from_tensor_slices(([0, 1, 2, 3], ()))
    dataset = dataset.padded_batch(2)
    self.assertDatasetProduces(dataset, [([0, 1], ()), ([2, 3], ())])

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchWithNoneElement(self):
    dataset = dataset_ops.Dataset.from_tensor_slices(([0, 1, 2, 3], None))
    with self.assertRaises(TypeError):
      dataset = dataset.padded_batch(2)

  @combinations.generate(test_base.default_test_combinations())
  def testDefaultPaddedShapes(self):

    def fill(x):
      return array_ops.fill([x], x)

    dataset = (
        dataset_ops.Dataset.from_tensor_slices(
            [1, 2, 3, 4]).map(fill).padded_batch(batch_size=2))
    self.assertDatasetProduces(
        dataset,
        expected_output=[[[1, 0], [2, 2]], [[3, 3, 3, 0], [4, 4, 4, 4]]])

  @combinations.generate(test_base.default_test_combinations())
  def testNestedDefaultPaddedShapes(self):

    def fill_tuple(x):
      return (x, array_ops.fill([x], x))

    dataset = (
        dataset_ops.Dataset.from_tensor_slices(
            [1, 2, 3, 4]).map(fill_tuple).padded_batch(batch_size=2))
    self.assertDatasetProduces(
        dataset,
        expected_output=[([1, 2], [[1, 0], [2, 2]]),
                         ([3, 4], [[3, 3, 3, 0], [4, 4, 4, 4]])])

  @combinations.generate(
      combinations.times(
          test_base.default_test_combinations(),
          combinations.combine(
              padding_values=[(-1, '<end>', {'structure': ''}),
                              (-1, '<end>', None)])))
  def testPaddedBatchDatasetNonDefaultPadding(self, padding_values):

    def fill_tuple(x):
      filled = array_ops.fill([x], x)
      return (filled, string_ops.as_string(filled), {
          'structure': string_ops.as_string(filled)
      })

    random_seq_lens = np.random.randint(20, size=(32,)).astype(np.int32)
    dataset = (
        dataset_ops.Dataset.from_tensor_slices(random_seq_lens).map(fill_tuple)
        .padded_batch(
            4, padded_shapes=([-1], [-1], {'structure': [-1]}),
            padding_values=padding_values))

    get_next = self.getNext(dataset)
    for i in range(8):
      result = self.evaluate(get_next())
      padded_len = np.max(result[0])
      self.assertEqual((4, padded_len), result[0].shape)
      self.assertEqual((4, padded_len), result[1].shape)
      self.assertEqual((4, padded_len), result[2]['structure'].shape)
      for j in range(4):
        seq_len = random_seq_lens[(i * 4) + j]
        self.assertAllEqual(result[0][j, :seq_len], [seq_len] * seq_len)
        self.assertAllEqual(result[0][j, seq_len:],
                            [-1] * (padded_len - seq_len))
        self.assertAllEqual(result[1][j, :seq_len],
                            [compat.as_bytes(str(seq_len))] * seq_len)
        self.assertAllEqual(result[1][j, seq_len:],
                            [b'<end>'] * (padded_len - seq_len))
        self.assertAllEqual(result[2]['structure'][j, :seq_len],
                            [compat.as_bytes(str(seq_len))] * seq_len)
        self.assertAllEqual(result[2]['structure'][j, seq_len:],
                            [b''] * (padded_len - seq_len))
    with self.assertRaises(errors.OutOfRangeError):
      self.evaluate(get_next())

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchDatasetUnicode(self):
    # See GitHub issue 16149
    def generator():
      data = [[u'Простой', u'тест', u'юникода'],
              [u'никогда', u'не', u'бывает', u'простым']]

      for seq in data:
        yield seq, [0, 1, 2, 3]

    dataset = dataset_ops.Dataset.from_generator(
        generator, (dtypes.string, dtypes.int32),
        (tensor_shape.TensorShape([None]), tensor_shape.TensorShape([None])))
    padded_dataset = dataset.padded_batch(
        2, padded_shapes=([None], [None]), padding_values=('', 0))
    next_element = self.getNext(padded_dataset)
    self.evaluate(next_element())

  @combinations.generate(test_base.graph_only_combinations())
  def testPaddedBatchDatasetShapeSpecifications(self):
    int_placeholder = array_ops.placeholder(dtypes.int32)
    float_placeholder = array_ops.placeholder(dtypes.float32)
    string_placeholder = array_ops.placeholder(dtypes.string)
    input_dataset = dataset_ops.Dataset.from_tensors(
        (int_placeholder, float_placeholder, string_placeholder))

    # Test different ways of specifying the `padded_shapes` argument.
    dynamic_padding_from_tensor_shapes = input_dataset.padded_batch(
        32,
        padded_shapes=(tensor_shape.TensorShape([None]),
                       tensor_shape.TensorShape([None, None]),
                       tensor_shape.TensorShape([37])))
    dynamic_padding_from_lists = input_dataset.padded_batch(
        32, padded_shapes=([None], [None, None], [37]))
    dynamic_padding_from_lists_with_minus_one = input_dataset.padded_batch(
        32, padded_shapes=([-1], [-1, -1], [37]))
    dynamic_padding_from_tensors = input_dataset.padded_batch(
        32,
        padded_shapes=(constant_op.constant([-1], dtype=dtypes.int64),
                       constant_op.constant([-1, -1], dtype=dtypes.int64),
                       constant_op.constant([37], dtype=dtypes.int64)))

    for dataset in [
        dynamic_padding_from_tensor_shapes, dynamic_padding_from_lists,
        dynamic_padding_from_lists_with_minus_one, dynamic_padding_from_tensors
    ]:
      dataset_output_shapes = dataset_ops.get_legacy_output_shapes(dataset)
      self.assertEqual([None, None], dataset_output_shapes[0].as_list())
      self.assertEqual([None, None, None], dataset_output_shapes[1].as_list())
      self.assertEqual([None, 37], dataset_output_shapes[2].as_list())

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchSparseError(self):

    st = sparse_tensor.SparseTensorValue(
        indices=[[0, 0]], values=([42]), dense_shape=[1, 1])

    with self.assertRaises(TypeError):
      _ = dataset_ops.Dataset.from_tensors(st).repeat(10).padded_batch(10)

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchRaggedError(self):

    rt = ragged_tensor_value.RaggedTensorValue(
        np.array([0, 42]), np.array([0, 2], dtype=np.int64))

    with self.assertRaises(TypeError):
      _ = dataset_ops.Dataset.from_tensors(rt).repeat(10).padded_batch(10)

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchShapeErrorWrongRank(self):
    with self.assertRaisesRegex(
        ValueError, r'The padded shape \(1,\) is not compatible with the '
        r'corresponding input component shape \(\).'):
      _ = dataset_ops.Dataset.range(10).padded_batch(5, padded_shapes=[1])

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchShapeErrorTooSmall(self):
    with self.assertRaisesRegex(
        ValueError, r'The padded shape \(1,\) is not compatible with the '
        r'corresponding input component shape \(3,\).'):
      _ = dataset_ops.Dataset.from_tensors([1, 2, 3]).padded_batch(
          5, padded_shapes=[1])

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchShapeErrorShapeNotRank1(self):
    with self.assertRaisesRegex(
        ValueError, r'Padded shape .* must be a 1-D tensor '
        r'of tf.int64 values, but its shape was \(2, 2\).'):
      _ = dataset_ops.Dataset.from_tensors([1, 2, 3]).padded_batch(
          5, padded_shapes=[[1, 1], [1, 1]])

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchShapeErrorShapeNotInt(self):
    with self.assertRaisesRegex(
        TypeError, r'Padded shape .* must be a 1-D tensor '
        r'of tf.int64 values, but its element type was float32.'):
      _ = dataset_ops.Dataset.from_tensors([1, 2, 3]).padded_batch(
          5, padded_shapes=constant_op.constant([1.5, 2., 3.]))

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchShapeErrorWrongRankFromTensor(self):
    with self.assertRaisesRegex(
        ValueError, r'The padded shape \(1,\) is not compatible with the '
        r'corresponding input component shape \(\).'):
      shape_as_tensor = constant_op.constant([1], dtype=dtypes.int64)
      _ = dataset_ops.Dataset.range(10).padded_batch(
          5, padded_shapes=shape_as_tensor)

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchShapeErrorDefaultShapeWithUnknownRank(self):
    with self.assertRaisesRegex(ValueError, r'`padded_shapes`.*unknown rank'):
      ds = dataset_ops.Dataset.from_generator(
          lambda: iter([1, 2, 3]), output_types=dtypes.int32)
      ds.padded_batch(2)

  @combinations.generate(test_base.graph_only_combinations())
  def testPaddedBatchShapeErrorPlaceholder(self):
    with self.assertRaisesRegex(
        ValueError,
        r'The padded shape \((\?|None), (\?|None)\) is not compatible with the '
        r'corresponding input component shape \(\).'):
      shape_as_tensor = array_ops.placeholder(dtypes.int64, shape=[2])
      _ = dataset_ops.Dataset.range(10).padded_batch(
          5, padded_shapes=shape_as_tensor)

  @combinations.generate(test_base.default_test_combinations())
  def testPaddedBatchBfloat16(self):
    ds = dataset_ops.Dataset.range(5)
    ds = ds.map(lambda x: math_ops.cast(x, dtypes.bfloat16))
    ds = ds.padded_batch(10)
    self.assertDatasetProduces(
        ds, expected_output=[[0.0, 1.0, 2.0, 3.0, 4.0]])

  @combinations.generate(test_base.default_test_combinations())
  def testDefaultPaddedValueShapes(self):

    def fill(x):
      return array_ops.fill([x], x)

    dataset = dataset_ops.Dataset.zip(
        (dataset_ops.Dataset.from_tensor_slices([1, 2, 3, 4]).map(fill),
         dataset_ops.Dataset.from_tensor_slices([1, 2, 3, 4]).map(fill)))
    dataset = dataset.padded_batch(batch_size=2, padding_values=-1)
    self.assertDatasetProduces(
        dataset,
        expected_output=[([[1, -1], [2, 2]], [[1, -1], [2, 2]]),
                         ([[3, 3, 3, -1], [4, 4, 4, 4]], [[3, 3, 3, -1],
                                                          [4, 4, 4, 4]])])

  @combinations.generate(test_base.default_test_combinations())
  def testName(self):
    dataset = dataset_ops.Dataset.range(5).padded_batch(5, name='padded_batch')
    self.assertDatasetProduces(dataset, [list(range(5))])


class PaddedBatchCheckpointTest(checkpoint_test_base.CheckpointTestBase,
                                parameterized.TestCase):

  @combinations.generate(
      combinations.times(test_base.default_test_combinations(),
                         checkpoint_test_base.default_test_combinations()))
  def test(self, verify_fn):

    def build_dataset(seq_lens):
      return dataset_ops.Dataset.from_tensor_slices(seq_lens).map(
          lambda x: array_ops.fill([x], x)).padded_batch(
              batch_size=4, padded_shapes=[-1])

    seq_lens = np.random.randint(1, 20, size=(32,)).astype(np.int32)
    verify_fn(self, lambda: build_dataset(seq_lens), num_outputs=8)

  @combinations.generate(
      combinations.times(test_base.default_test_combinations(),
                         checkpoint_test_base.default_test_combinations()))
  def testNonDefaultPadding(self, verify_fn):

    def build_dataset(seq_lens):

      def fill_tuple(x):
        filled = array_ops.fill([x], x)
        return (filled, string_ops.as_string(filled))

      padded_shape = [-1]
      return dataset_ops.Dataset.from_tensor_slices(seq_lens).map(
          fill_tuple).padded_batch(
              batch_size=4,
              padded_shapes=(padded_shape, padded_shape),
              padding_values=(-1, '<end>'))

    seq_lens = np.random.randint(1, 20, size=(32,)).astype(np.int32)
    verify_fn(self, lambda: build_dataset(seq_lens), num_outputs=8)


if __name__ == '__main__':
  test.main()
