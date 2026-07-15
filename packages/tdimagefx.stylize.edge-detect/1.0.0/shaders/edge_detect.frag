layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uRadius;
uniform float uStrength;
uniform float uThreshold;
uniform float uSoftness;
uniform float uInvert;
uniform float uColorAmount;

float sampleLuma(vec2 uv)
{
    return dot(texture(sTD2DInputs[0], uv).rgb, vec3(0.2126, 0.7152, 0.0722));
}

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 stepUV = vec2(1.0) / max(uTD2DInfos[0].res.zw, vec2(1.0)) * max(uRadius, 0.0);
    float topLeft = sampleLuma(uv + vec2(-stepUV.x, stepUV.y));
    float top = sampleLuma(uv + vec2(0.0, stepUV.y));
    float topRight = sampleLuma(uv + stepUV);
    float left = sampleLuma(uv + vec2(-stepUV.x, 0.0));
    float right = sampleLuma(uv + vec2(stepUV.x, 0.0));
    float bottomLeft = sampleLuma(uv - stepUV);
    float bottom = sampleLuma(uv + vec2(0.0, -stepUV.y));
    float bottomRight = sampleLuma(uv + vec2(stepUV.x, -stepUV.y));
    float gradientX = -topLeft + topRight - 2.0 * left + 2.0 * right - bottomLeft + bottomRight;
    float gradientY = topLeft + 2.0 * top + topRight - bottomLeft - 2.0 * bottom - bottomRight;
    float magnitude = length(vec2(gradientX, gradientY)) * max(uStrength, 0.0);
    float edge = smoothstep(uThreshold, uThreshold + max(uSoftness, 0.0001), magnitude);
    edge = mix(edge, 1.0 - edge, clamp(uInvert, 0.0, 1.0));
    vec3 edgeColor = mix(vec3(edge), source.rgb * edge, clamp(uColorAmount, 0.0, 1.0));
    vec4 effect = vec4(edgeColor, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
