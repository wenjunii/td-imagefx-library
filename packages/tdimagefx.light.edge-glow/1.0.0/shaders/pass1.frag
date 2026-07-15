layout(location = 0) out vec4 fragColor;

uniform float uEdgeWidth;
uniform float uThreshold;
uniform vec4 uGlowColor;

float luminanceAt(vec2 uv)
{
    vec3 color = texture(sTD2DInputs[0], clamp(uv, vec2(0.0), vec2(1.0))).rgb;
    return dot(color, vec3(0.2126, 0.7152, 0.0722));
}

void main()
{
    vec2 uv = vUV.st;
    vec2 texel = max(uEdgeWidth, 0.5) / max(uTD2DInfos[0].res.zw, vec2(1.0));
    float tl = luminanceAt(uv + texel * vec2(-1.0, 1.0));
    float tc = luminanceAt(uv + texel * vec2(0.0, 1.0));
    float tr = luminanceAt(uv + texel * vec2(1.0, 1.0));
    float ml = luminanceAt(uv + texel * vec2(-1.0, 0.0));
    float mr = luminanceAt(uv + texel * vec2(1.0, 0.0));
    float bl = luminanceAt(uv + texel * vec2(-1.0, -1.0));
    float bc = luminanceAt(uv + texel * vec2(0.0, -1.0));
    float br = luminanceAt(uv + texel * vec2(1.0, -1.0));
    float gx = -tl - 2.0 * ml - bl + tr + 2.0 * mr + br;
    float gy = -bl - 2.0 * bc - br + tl + 2.0 * tc + tr;
    float edge = length(vec2(gx, gy));
    edge = smoothstep(max(uThreshold, 0.0), max(uThreshold, 0.0) + 0.15, edge);
    float alpha = texture(sTD2DInputs[0], uv).a;
    fragColor = TDOutputSwizzle(vec4(uGlowColor.rgb * edge, alpha));
}
