layout(location = 0) out vec4 fragColor;

// The hash12 function below is from David Hoskins' "Hash without Sine".
// Copyright (c) 2014 David Hoskins
// Original source: https://www.shadertoy.com/view/4djSRW
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

uniform float uMix;
uniform float uTime;
uniform float uAmount;
uniform float uBlockSize;
uniform float uRate;
uniform float uSeed;

float hash12(vec2 p)
{
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

void main()
{
    vec2 uv = vUV.st;
    vec2 resolution = uTD2DInfos[0].res.zw;
    float blockSize = max(2.0, uBlockSize);
    vec2 block = floor(uv * resolution / blockSize);
    float frame = floor(uTime * max(uRate, 0.0));
    float randomValue = hash12(block + vec2(frame, uSeed));
    float gate = step(0.72, randomValue);
    float shift = (hash12(block.yx + vec2(uSeed, frame)) * 2.0 - 1.0) * uAmount * gate;
    vec2 shiftedUV = uv + vec2(shift, 0.0);
    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effect = texture(sTD2DInputs[0], shiftedUV);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
