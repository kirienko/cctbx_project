#ifndef SCITBX_MATH_ERF_H
#define SCITBX_MATH_ERF_H

#include <scitbx/math/erf/engine.h>
#include <scitbx/array_family/shared.h>
#include <scitbx/array_family/ref.h>

namespace scitbx { namespace math {

  //! Approximate values for erf(x).
  /*! See also: scitbx::math::erf_engine
   */
  template <typename FloatType>
  inline
  FloatType
  erf(FloatType const& x)
  {
    return erf_engine<FloatType>().compute(x, 0);
  }

  template <typename FloatType>
  inline
  scitbx::af::shared<FloatType>
  erf( scitbx::af::const_ref<FloatType> const& x)
  {
     scitbx::af::shared<FloatType> result(x.size(),0);
     for( unsigned ii=0;ii<x.size();ii++){
       result[ii]=erf_engine<FloatType>().compute(x[ii], 0);
     }
     return ( result );
  }


  //! Approximate values for erfc(x).
  /*! See also: scitbx::math::erf_engine
   */
  template <typename FloatType>
  inline
  FloatType
  erfc(FloatType const& x)
  {
    return erf_engine<FloatType>().compute(x, 1);
  }

  //! Approximate values for exp(x*x) * erfc(x).
  /*! See also: scitbx::math::erf_engine
   */
  template <typename FloatType>
  inline
  FloatType
  erfcx(FloatType const& x)
  {
    return erf_engine<FloatType>().compute(x, 2);
  }

}} // namespace scitbx::math

#endif // SCITBX_MATH_ERF_H
