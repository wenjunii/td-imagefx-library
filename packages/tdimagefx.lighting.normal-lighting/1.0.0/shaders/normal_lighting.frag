uniform float uMix; uniform float uLightX; uniform float uLightY; uniform float uLightZ; uniform float uAmbient; uniform float uStrength;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec4 src = texture(sTD2DInputs[0], uv); vec3 normal = normalize(texture(sTD2DInputs[1], uv).rgb * 2.0 - 1.0);
    vec3 lightDir = normalize(vec3(uLightX,uLightY,max(.001,uLightZ))); float diffuse = max(dot(normal, lightDir),0.0);
    vec3 lit = src.rgb * (uAmbient + diffuse * uStrength);
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, lit, clamp(uMix,0.0,1.0)), src.a));
}
